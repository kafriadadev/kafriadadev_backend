"""The HTML shell around a one-time code, sent by email.

Table-based layout and inline styles throughout — this has to render in Gmail,
Outlook and everything between, none of which reliably support a <style>
block or modern CSS. Colours are the same document tokens the web app uses for
anything that must not invert in dark mode (see globals.css, --plate-*): an
email client's dark mode is not ours to hand a code over to.

Every value interpolated here is one this service generated itself (a six-digit
code, an integer, a fixed purpose string) — nothing a caller typed reaches this
template, so there is nothing here to escape.
"""

from __future__ import annotations

_COPY = {
    "phone_verification": {
        "eyebrow": "CONFIRM YOUR NUMBER",
        "heading": "Your confirmation code",
        "instructions": (
            "Enter this code to confirm your phone number and finish registration."
        ),
    },
    "password_reset": {
        "eyebrow": "PASSWORD RESET",
        "heading": "Reset your password",
        "instructions": "Enter this code to reset your KAFRIADA password.",
    },
}


def otp_email_html(*, code: str, minutes: int, purpose: str) -> str:
    copy = _COPY[purpose]
    return f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{copy["heading"]}</title>
  </head>
  <body style="margin:0; padding:0; background-color:#F7F5EF;">
    <div style="display:none; max-height:0; overflow:hidden; opacity:0;">
      {copy["heading"]} &ndash; KAFRIADA
    </div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background-color:#F7F5EF;">
      <tr>
        <td align="center" style="padding:32px 16px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                 style="max-width:480px; background-color:#FFFDF7;
                        border:1px solid #DCD7C8; border-radius:5px;">
            <tr>
              <td style="padding:28px 32px 20px; border-bottom:2px solid #141815;">
                <span style="font-family:Arial,Helvetica,sans-serif; font-weight:700;
                             font-size:16px; letter-spacing:3px; text-transform:uppercase;
                             color:#141815;">
                  KAF<span style="color:#0E4429;">RIADA</span>
                </span>
                <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px;
                            letter-spacing:1.5px; text-transform:uppercase;
                            color:#5A6158; margin-top:6px;">
                  Jigawa State &middot; Pilot
                </div>
              </td>
            </tr>
            <tr>
              <td style="padding:28px 32px 8px;">
                <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px;
                            letter-spacing:1.5px; text-transform:uppercase;
                            color:#6E5100; font-weight:700;">
                  {copy["eyebrow"]}
                </div>
                <h1 style="font-family:Georgia,'Times New Roman',serif; font-size:24px;
                           line-height:1.3; color:#141815; margin:8px 0 0;
                           font-weight:400;">
                  {copy["heading"]}
                </h1>
              </td>
            </tr>
            <tr>
              <td style="padding:12px 32px 0;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                       style="background-color:#E3ECE5; border:1px solid #C2BBA6;
                              border-radius:3px;">
                  <tr>
                    <td align="center" style="padding:20px 16px;">
                      <span style="font-family:'Courier New',monospace; font-size:32px;
                                   font-weight:700; letter-spacing:10px; color:#0E4429;">
                        {code}
                      </span>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px 4px; font-family:Arial,Helvetica,sans-serif;
                         font-size:14px; line-height:1.6; color:#141815;">
                {copy["instructions"]} It expires in {minutes} minutes.
              </td>
            </tr>
            <tr>
              <td style="padding:4px 32px 28px; font-family:Arial,Helvetica,sans-serif;
                         font-size:13px; line-height:1.6; color:#5A6158;">
                KAFRIADA will never call, text or email you asking for this code.
              </td>
            </tr>
            <tr>
              <td style="padding:16px 32px; border-top:1px solid #DCD7C8;
                         font-family:Arial,Helvetica,sans-serif; font-size:11px;
                         letter-spacing:.5px; color:#8A9086;">
                Jigawa State Sports ID Pilot &middot; This is an automated message.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
