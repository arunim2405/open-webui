import logging

from fastapi import APIRouter, Depends, HTTPException, status
from open_webui.internal.db import get_session
from open_webui.models.signup_codes import SignupCodeModel, SignupCodes
from open_webui.utils.auth import get_admin_user
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

router = APIRouter()


############################
# GenerateCodes
############################


class GenerateCodesForm(BaseModel):
    count: int = Field(default=1, ge=1, le=1000)


@router.post('/generate', response_model=list[SignupCodeModel])
async def generate_codes(
    form_data: GenerateCodesForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    return SignupCodes.generate_codes(form_data.count, db=db)


############################
# GetCodes
############################


@router.get('/', response_model=list[SignupCodeModel])
async def get_codes(user=Depends(get_admin_user), db: Session = Depends(get_session)):
    return SignupCodes.get_codes(db=db)


############################
# DeleteCode
############################


@router.delete('/{code}', response_model=bool)
async def delete_code(code: str, user=Depends(get_admin_user), db: Session = Depends(get_session)):
    existing = SignupCodes.get_code(code, db=db)
    if not existing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail='Signup code not found')
    if existing.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail='Used signup codes cannot be deleted')
    return SignupCodes.delete_code(code, db=db)
