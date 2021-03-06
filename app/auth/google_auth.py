from flask import Blueprint, request, render_template, \
    flash, g, session, redirect, make_response, url_for

from app.db import db
from authlib.client import OAuth2Session
from app.auth.models import User
from config import settings
import functools

import google.oauth2.credentials
import googleapiclient.discovery

from googleads import adwords, oauth2

ACCESS_TOKEN_URI = settings.ACCESS_TOKEN_URI
AUTHORIZATION_URL = settings.AUTHORIZATION_URL
AUTHORIZATION_SCOPE = settings.AUTHORIZATION_SCOPE
AUTH_REDIRECT_URI = settings.AUTH_REDIRECT_URI
BASE_URI = settings.BASE_URI
CLIENT_ID = settings.CLIENT_ID
CLIENT_SECRET = settings.CLIENT_SECRET
AUTH_TOKEN_KEY = settings.AUTH_TOKEN_KEY
AUTH_STATE_KEY = settings.AUTH_STATE_KEY
DEVELOPER_TOKEN = settings.DEVELOPER_TOKEN
CLIENT_CUSTOMER_ID = settings.CLIENT_CUSTOMER_ID

google_auth = Blueprint('google_auth', __name__, url_prefix='/google')


def init_app(app):
    app.register_blueprint(google_auth)


def is_logged_in():
    return True if AUTH_TOKEN_KEY in session else False


def build_credentials():
    if not is_logged_in():
        raise Exception('User must be logged in')

    oauth2_tokens = session[AUTH_TOKEN_KEY]

    return google.oauth2.credentials.Credentials(
        oauth2_tokens['access_token'],
        refresh_token=oauth2_tokens['refresh_token'],
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri=ACCESS_TOKEN_URI)


def get_user_info():
    credentials = build_credentials()

    oauth2_client = googleapiclient.discovery.build(
        'oauth2', 'v2', credentials=credentials
    )

    return oauth2_client.userinfo().get().execute()

def get_webmasters_service():
    credentials = build_credentials()
    webmasters_service = googleapiclient.discovery.build(
        'webmasters', 'v3', credentials=credentials
    )
    return webmasters_service

def get_adwords_client():
    oauth2_tokens = session[AUTH_TOKEN_KEY]
    oauth2_client = oauth2.GoogleRefreshTokenClient(
        CLIENT_ID,
        CLIENT_SECRET,
        oauth2_tokens['refresh_token']
    )
    adwords_client = adwords.AdWordsClient(
        DEVELOPER_TOKEN, oauth2_client, 'Celebration Saunas', client_customer_id=CLIENT_CUSTOMER_ID
    )

    return adwords_client

def no_cache(view):
    @functools.wraps(view)
    def no_cache_impl(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'  # noqa
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    return functools.update_wrapper(no_cache_impl, view)


@google_auth.route('/login')
@no_cache
def login():
    auth_session = OAuth2Session(CLIENT_ID, CLIENT_SECRET,
                            scope=AUTHORIZATION_SCOPE,
                            redirect_uri=AUTH_REDIRECT_URI)

    uri, state = auth_session.authorization_url(AUTHORIZATION_URL)

    session[AUTH_STATE_KEY] = state
    session.permanent = True

    return redirect(uri, code=302)

@google_auth.route('/auth')
@no_cache
def google_auth_redirect():
    req_state = request.args.get('state', default=None, type=None)

    if req_state != session[AUTH_STATE_KEY]:
        response = make_response('Invalid state parameter', 401)
        return response

    auth_session = OAuth2Session(CLIENT_ID, CLIENT_SECRET,
                            scope=AUTHORIZATION_SCOPE,
                            state=session[AUTH_STATE_KEY],
                            redirect_uri=AUTH_REDIRECT_URI)

    oauth2_tokens = auth_session.fetch_access_token(
        ACCESS_TOKEN_URI,
        authorization_response=request.url
    )

    session[AUTH_TOKEN_KEY] = oauth2_tokens

    user_info = get_user_info()
    users = User.query.filter_by(email=user_info['email']).all()

    user = {
        "name": user_info['name'],
        "family_name": user_info['family_name'],
        "picture": user_info['picture'],
        "locale": user_info['locale'],
        "email": user_info['email'],
        "given_name": user_info['given_name'],
        "id": user_info['id'],
        "verified_email": user_info['verified_email']
    }

    if len(users) < 1:
        user = User(user)
        db.session.add(user)
        db.session.commit()

    return redirect(BASE_URI, code=302)


@google_auth.route('/logout')
@no_cache
def logout():
    session.pop(AUTH_TOKEN_KEY, None)
    session.pop(AUTH_STATE_KEY, None)

    return redirect(BASE_URI, code=302)
