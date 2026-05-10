import resend
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self.resend_api_key = settings.RESEND_API_KEY
        self.frontend_url = settings.FRONTEND_URL
        if self.resend_api_key:
            resend.api_key = self.resend_api_key

    async def send_password_reset_email(self, email: str, token: str) -> bool:
        if not self.resend_api_key:
            logger.warning("RESEND_API_KEY not configured, skipping email")
            return False

        try:
            reset_url = f"{self.frontend_url}/reset-password?token={token}"
            
            response = resend.Emails.send({
                "from": f"Simulador Inversiones <noreply@{settings.FRONTEND_URL.replace('https://', '')}>",
                "to": email,
                "subject": "Restablece tu contraseña - Simulador de Inversiones",
                "html": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; padding: 20px;">
                    <div style="max-width: 480px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <div style="text-align: center; margin-bottom: 24px;">
                            <h1 style="color: #0f172a; font-size: 24px; font-weight: 700; margin: 0;">Simulador de Inversiones</h1>
                        </div>
                        
                        <h2 style="color: #1e293b; font-size: 20px; font-weight: 600; margin: 0 0 16px 0;">Restablece tu contraseña</h2>
                        
                        <p style="color: #64748b; font-size: 14px; line-height: 1.6; margin: 0 0 24px 0;">
                            Has solicitado restablecer tu contraseña. Haz clic en el botón de abajo para crear una nueva contraseña.
                        </p>
                        
                        <div style="text-align: center; margin-bottom: 24px;">
                            <a href="{reset_url}" style="display: inline-block; background: #0f172a; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 14px;">
                                Restablecer Contraseña
                            </a>
                        </div>
                        
                        <p style="color: #94a3b8; font-size: 12px; line-height: 1.6; margin: 0 0 16px 0;">
                            Este enlace expirará en <strong>1 hora</strong>. Si no solicitaste este cambio, puedes ignorar este correo.
                        </p>
                        
                        <div style="border-top: 1px solid #e2e8f0; padding-top: 16px; margin-top: 24px;">
                            <p style="color: #94a3b8; font-size: 11px; margin: 0;">
                                Este es un correo automático del Simulador de Inversiones. Por favor no respondas a este mensaje.
                            </p>
                        </div>
                    </div>
                </body>
                </html>
                """
            })
            
            logger.info(f"Password reset email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send password reset email: {e}")
            return False

    async def send_verification_code(self, email: str, code: str, code_type: str = "2fa") -> bool:
        if not self.resend_api_key:
            logger.warning("RESEND_API_KEY not configured, skipping email")
            return False

        try:
            subject = "Código de verificación - 2FA" if code_type == "2fa" else "Verifica tu correo electrónico"
            
            response = resend.Emails.send({
                "from": f"Simulador Inversiones <noreply@{settings.FRONTEND_URL.replace('https://', '')}>",
                "to": email,
                "subject": subject,
                "html": f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; padding: 20px;">
                    <div style="max-width: 480px; margin: 0 auto; background: white; border-radius: 12px; padding: 32px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                        <div style="text-align: center; margin-bottom: 24px;">
                            <h1 style="color: #0f172a; font-size: 24px; font-weight: 700; margin: 0;">Simulador de Inversiones</h1>
                        </div>
                        
                        <h2 style="color: #1e293b; font-size: 20px; font-weight: 600; margin: 0 0 16px 0;">Tu código de verificación</h2>
                        
                        <div style="background: #f1f5f9; border-radius: 8px; padding: 20px; text-align: center; margin: 24px 0;">
                            <p style="color: #64748b; font-size: 14px; margin: 0 0 12px 0;">Ingresa este código:</p>
                            <p style="color: #0f172a; font-size: 32px; font-weight: 700; margin: 0; letter-spacing: 8px;">{code}</p>
                        </div>
                        
                        <p style="color: #94a3b8; font-size: 12px; margin: 0;">
                            Este código expirará en <strong>10 minutos</strong>.
                        </p>
                    </div>
                </body>
                </html>
                """
            })
            
            logger.info(f"Verification code email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send verification code email: {e}")
            return False


email_service = EmailService()