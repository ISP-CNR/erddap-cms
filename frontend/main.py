import os
from flask import Flask, url_for, make_response
from flask_multipass import Multipass
import utils
import logging
from flask_simple_captcha import CAPTCHA
from flask_mail import Mail

app = Flask(__name__, static_url_path = utils.URL_PATH)
multipass = Multipass()

class ReverseProxied(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        scheme = environ.get('HTTP_X_FORWARDED_PROTO')
        if scheme:

            environ['wsgi.url_scheme'] = scheme
        return self.app(environ, start_response)
app.wsgi_app = ReverseProxied(app.wsgi_app)

app.mailer = Mail(app)

app.config.update(
  SECRET_KEY = '5586a9f0d5ce4fc8a4cd6d87af671df6af01b4cd1aeaf5e758f6de6cbc35dce7',
  SESSION_COOKIE_SECURE = False if app.debug else True
)

app.config['MAX_CONTENT_LENGTH'] = 2048 * 1024 * 1024
app.config['UPLOAD_EXTENSIONS'] = ['.csv', '.nc']

@app.errorhandler(413)
def request_entity_too_large(error):
    return make_response({"result": "error",
                 "message": 'File size too large'}, 413)

# initialize multipass
app.config.from_pyfile('multipass.cfg')


# fix MULTIPASS_LOGIN_URLS with URL_PATH
app.config.update(
    MULTIPASS_LOGIN_URLS=[f"{utils.URL_PATH}/login", f'{utils.URL_PATH}/login/<provider>']
  )
# fix MULTIPASS_AUTH_PROVIDERS with URL_PATH
for provider, config in app.config['MULTIPASS_AUTH_PROVIDERS'].items():
      config.update({'callback_uri': f"{utils.URL_PATH}/multipass/authlib/{provider}"})

# CAPTCHA inizialization

CAPTCHA_CONFIG = {
  'SECRET_CAPTCHA_KEY': '38pEOPt*2n@LUpD0',  # use for JWT encoding/decoding

  # CAPTCHA GENERATION SETTINGS
  'EXPIRE_SECONDS': 60 * 10,  # takes precedence over EXPIRE_MINUTES
  'CAPTCHA_IMG_FORMAT': 'JPEG',  # 'PNG' or 'JPEG' (JPEG is 3X faster)

  # CAPTCHA TEXT SETTINGS
  'CAPTCHA_LENGTH': 6,  # Length of the generated CAPTCHA text
  'CAPTCHA_DIGITS': False,  # Should digits be added to the character pool?
  'EXCLUDE_VISUALLY_SIMILAR': True,  # Exclude visually similar characters
  'BACKGROUND_COLOR': (33, 37, 41),  # RGB(A?) background color (default black)
  'TEXT_COLOR': (255, 255, 255),  # RGB(A?) text color (default white)

  # Optional settings
  #'ONLY_UPPERCASE': True, # Only use uppercase characters
  #'CHARACTER_POOL': 'AaBb',  # Use a custom character pool
}

SIMPLE_CAPTCHA = CAPTCHA(config=CAPTCHA_CONFIG)
app = SIMPLE_CAPTCHA.init_app(app)


app.config['MAIL_SERVER']= os.environ['ERDDAP_emailSmtpHost'] 
app.config['MAIL_PORT'] = os.environ['ERDDAP_emailSmtpPort']
app.config['MAIL_USERNAME'] = os.environ['ERDDAP_emailUserName']
app.config['MAIL_PASSWORD'] = os.environ['ERDDAP_emailPassword']
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] =  os.environ['ERDDAP_emailUseSSL']


import multiauth
import routes
import api