from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select
from db.models import User, UserType, LoginSession
from schemas.auth import UserInfo, UserCreate, UserAuth, Logout, RefreshToken, LoginWithGoogle
from db.database import get_session
from utils.security import verify_password, hash_password
from utils.auth_helper import create_login_session, create_token_from_user, decode_token, is_session_valid
import datetime
from utils import constants
from utils.procedures import CustomError
from dependencies.auth_dependencies import get_current_user_dependency
import os
import requests


router = APIRouter(prefix='/apps/auth', tags=['auth'])


@router.post('/login')
def login_with_email(user_auth: UserAuth, db: Session = Depends(get_session)):

    query = select(User).where(User.email == user_auth.email)
    user = db.exec(query).first()

    if not user or not user.password or not verify_password(user_auth.password, user.password) or user.user_type != UserType.NORMAL_USER:
        raise CustomError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            message='Invalid email or password.'
        )

    if user.is_blocked:
        raise CustomError(
            status_code=status.HTTP_403_FORBIDDEN,
            message='Forbidden.'
        )

    exp = datetime.datetime.now(datetime.UTC) + constants.ACCESS_TOKEN_LIFETIME_DELTA
    login_session = create_login_session(user, db, exp, user_auth.login_session_type)
    token, refresh_token = create_token_from_user(user, exp, login_session.id)

    user_data = UserInfo(
        id=user.id,
        name=user.name,
        email=user.email,
        image=user.image,
        is_email_verified=user.is_email_verified,
    )

    return {
        'token': token,
        'refresh_token': refresh_token,
        'user': user_data,
    }


@router.post('/login_google_desktop')
def login_with_google_desktop(login_google_obj: LoginWithGoogle, db: Session = Depends(get_session)):
    try:
        token_res = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": login_google_obj.code,
                "client_id": os.getenv("GOOGLE_LOGIN_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_LOGIN_CLIENT_SECRET"),
                "redirect_uri": os.getenv("GOOGLE_LOGIN_DESKTOP_REDIRECT_URI"),
                "grant_type": "authorization_code",
                "code_verifier": login_google_obj.code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if token_res.status_code != 200:
            raise CustomError(401, "Failed to exchange token")

        tokens = token_res.json()
        access_token = tokens["access_token"]

        response = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )

        if response.status_code != status.HTTP_200_OK:
            raise CustomError(status.HTTP_401_UNAUTHORIZED, 'Invalid_Google_Token')

        google_user = response.json()

        sub = google_user['sub']
        name = google_user['name']
        email = google_user['email']

        user = db.exec(select(User).where(User.google_user_id == sub)).first()
        if not user:
            user = db.exec(select(User).where(User.email == email)).first()
            if user:
                user.google_user_id = sub
                user.google_token = access_token
                user.is_email_verified = True

                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                user = User(
                    name=name,
                    email=email,
                    google_user_id=sub,
                    google_token=access_token,
                    is_email_verified=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)

        exp = datetime.datetime.now(datetime.UTC) + constants.ACCESS_TOKEN_LIFETIME_DELTA
        login_session = create_login_session(user, db, exp, login_google_obj.login_session_type)
        token, refresh_token = create_token_from_user(user, exp, login_session.id)

        user_data = UserInfo(
            id=user.id,
            name=user.name,
            email=user.email,
            image=user.image,
            is_email_verified=user.is_email_verified,
        )

        return {
            'token': token,
            'refresh_token': refresh_token,
            'user': user_data,
        }

    except Exception:
        raise CustomError(status.HTTP_500_INTERNAL_SERVER_ERROR, 'Error')


@router.get('/user_info')
def user_info(db: Session = Depends(get_session), user: User = Depends(get_current_user_dependency)):
    user_data = UserInfo(
        id=user.id,
        name=user.name,
        email=user.email,
        image=user.image,
        is_email_verified=user.is_email_verified,
    )

    return user_data


@router.post('/signup')
def signup(user_create: UserCreate, db: Session = Depends(get_session)):

    query = select(User).where(User.email == user_create.email)
    existing_user = db.exec(query).first()

    if existing_user:
        raise CustomError(
            status_code=status.HTTP_400_BAD_REQUEST,
            message='Email already registered'
        )

    hashed_password = hash_password(user_create.password)
    new_user = User(
        name=user_create.name,
        email=user_create.email,
        password=hashed_password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    exp = datetime.datetime.now(datetime.UTC) + constants.ACCESS_TOKEN_LIFETIME_DELTA
    login_session = create_login_session(new_user, db, exp, user_create.login_session_type)
    token, refresh_token = create_token_from_user(new_user, exp, login_session.id)

    user_data = UserInfo(
        id=new_user.id,
        name=new_user.name,
        email=new_user.email,
        image=new_user.image,
        is_email_verified=new_user.is_email_verified,
    )

    # TODO Send Email Verification

    return {
        'token': token,
        'refresh_token': refresh_token,
        'user': user_data,
    }


@router.post('/logout')
def logout(logout_obj: Logout, db: Session = Depends(get_session)):
    payload = decode_token(logout_obj.access_token)

    if payload.get('token_type') != 'access':
        raise CustomError(status.HTTP_400_BAD_REQUEST, 'Invalid_Token')

    if not is_session_valid(payload.get('session_id'), db):
        raise CustomError(status.HTTP_401_UNAUTHORIZED, 'Invalid_Token')

    query = select(LoginSession).where(LoginSession.id == payload.get('session_id'))
    login_session = db.exec(query).first()

    login_session.is_logged_out = True
    db.add(login_session)
    db.commit()
    db.refresh(login_session)

    return {
        'message': 'Success'
    }


@router.post('/refresh_token')
def refresh_current_token(refresh_obj: RefreshToken, db: Session = Depends(get_session)):
    payload = decode_token(refresh_obj.refresh_token)

    if payload.get('token_type') != 'refresh':
        raise CustomError(status.HTTP_400_BAD_REQUEST, 'Invalid_Token')

    if not is_session_valid(payload.get('session_id'), db):
        raise CustomError(status.HTTP_401_UNAUTHORIZED, 'Invalid_Token')

    u_query = select(User).where(User.id == payload.get('user_id'))
    user = db.exec(u_query).first()

    if not user:
        raise CustomError(status_code=status.HTTP_401_UNAUTHORIZED, message='Invalid_Token')

    s_query = select(LoginSession).where(LoginSession.id == payload.get('session_id'))
    login_session = db.exec(s_query).first()

    exp = payload.get('exp')
    dif = datetime.datetime.fromtimestamp(exp) - datetime.datetime.now()
    with_refresh = dif <= datetime.timedelta(hours=1)

    exp = datetime.datetime.now(datetime.UTC) + constants.ACCESS_TOKEN_LIFETIME_DELTA

    new_token, new_refresh = create_token_from_user(user, exp, login_session.id, with_refresh)

    login_session.expires_at = exp
    if with_refresh:
        login_session.refresh_expires_at = datetime.datetime.now(datetime.UTC) + constants.REFRESH_TOKEN_LIFETIME_DELTA

    db.add(login_session)
    db.commit()
    db.refresh(login_session)

    return {
        'new_token': new_token,
        'new_refresh': new_refresh
    }
