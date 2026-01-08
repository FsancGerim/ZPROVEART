from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

password = "invitado"

print(pwd_context.hash(password))
