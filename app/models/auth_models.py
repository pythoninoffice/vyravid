from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserSignUp(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    referral_code: Optional[str] = None

class UserSignIn(BaseModel):
    email: EmailStr
    password: str

class UserProfile(BaseModel):
    id: str  # Changed from UUID to str to match Supabase user IDs
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    avatar_character_id: Optional[str] = None
    watermark_logo_url: Optional[str] = None
    watermark_logo_gcs_path: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    type: Optional[str] = 'tester'  # User type from public.users table
    has_watched_tutorial: Optional[bool] = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    email_confirmed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: UserProfile
    expires_in: int

class TokenRefresh(BaseModel):
    refresh_token: str

class PasswordReset(BaseModel):
    email: EmailStr

class PasswordUpdate(BaseModel):
    password: str = Field(..., min_length=6)
    access_token: str

class EmailUpdate(BaseModel):
    email: EmailStr

class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    avatar_character_id: Optional[str] = None
    watermark_logo_url: Optional[str] = None
    watermark_logo_gcs_path: Optional[str] = None
    has_watched_tutorial: Optional[bool] = None

class ReferralCodeValidation(BaseModel):
    code: str

class ReferralCodeResponse(BaseModel):
    valid: bool
    message: str

class MagicLinkRequest(BaseModel):
    email: EmailStr
    redirect_to: Optional[str] = None

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    token: Optional[str] = None
    token_hash: Optional[str] = None
    type: str = "magiclink"  # or "email" for email verification
