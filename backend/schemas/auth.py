from typing import Optional
from pydantic import BaseModel


class UserBase(BaseModel):
    name: str
    email: str


class UserAuth(BaseModel):
    email: str
    password: str
    login_session_type: str = 'windows'


class UserCreate(UserBase):
    password: str
    login_session_type: str = 'windows'


class UserInfo(UserBase):
    id: str
    image: Optional[str] = None
    is_email_verified: bool


class Logout(BaseModel):
    access_token: str


class RefreshToken(BaseModel):
    refresh_token: str


class LoginWithGoogle(BaseModel):
    code: str
    code_verifier: str
    login_session_type: str = 'windows'
    # google_token: str
