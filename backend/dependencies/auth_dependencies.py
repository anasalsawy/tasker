from fastapi import Depends, status
from utils.auth_helper import decode_token
from fastapi.security import OAuth2PasswordBearer
from db.database import get_session
from sqlmodel import Session, select
from db.models import User, LoginSession
from utils.procedures import CustomError


oauth2_scheme = OAuth2PasswordBearer(tokenUrl='apps/auth/login')


def get_current_user_dependency(token: str = Depends(oauth2_scheme), db: Session = Depends(get_session)):
    try:
        payload = decode_token(token)
        user_id = payload.get('user_id')

        u_query = select(User).where(User.id == user_id)
        user = db.exec(u_query).first()

        if not user:
            raise CustomError(status_code=status.HTTP_401_UNAUTHORIZED, message='Invalid_Token')

        session_id = payload.get('session_id')
        s_query = select(LoginSession).where(LoginSession.id == session_id)
        login_session = db.exec(s_query).first()

        if not login_session or login_session.is_logged_out is True:
            raise CustomError(status_code=status.HTTP_401_UNAUTHORIZED, message='Invalid_Token')

        if user.is_blocked is True:
            raise CustomError(status_code=status.HTTP_403_FORBIDDEN, message='You_Are_Blocked')

        return user

    except Exception:
        raise CustomError(status_code=status.HTTP_401_UNAUTHORIZED, message='Invalid_Token')
