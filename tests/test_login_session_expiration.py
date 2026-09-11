import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault('SECRET_KEY', 'test-secret-key')
if 'DATABASE_PATH' not in os.environ:
    _temp_dir = tempfile.mkdtemp(prefix='outlookEmail-login-session-tests-')
    os.environ['DATABASE_PATH'] = os.path.join(_temp_dir, 'test.db')

web_outlook_app = importlib.import_module('web_outlook_app')
ROOT_DIR = Path(__file__).resolve().parents[1]


class FakePocketIdClient:
    def __init__(self, userinfo=None):
        self.userinfo = userinfo or {
            'sub': 'pocket-user-123',
            'email': 'user@example.com',
            'preferred_username': 'Pocket User',
        }
        self.redirect_uri = None
        self.state = None

    def authorize_redirect(self, redirect_uri, **kwargs):
        self.redirect_uri = redirect_uri
        self.state = kwargs.get('state')
        return web_outlook_app.redirect(
            f'https://sso.jackyccc.com/authorize?state={self.state}'
        )

    def authorize_access_token(self):
        return {
            'userinfo': self.userinfo,
            'id_token': 'validated-by-authlib-in-production',
            'access_token': 'test-token',
        }


class MissingIdTokenClient(FakePocketIdClient):
    def authorize_access_token(self):
        return {'userinfo': self.userinfo, 'access_token': 'untrusted-token'}


class LoginSessionExpirationTests(unittest.TestCase):
    def setUp(self):
        self.app = web_outlook_app.app
        self.previous_testing = self.app.config.get('TESTING')
        self.previous_csrf_enabled = self.app.config.get('WTF_CSRF_ENABLED')
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

        with self.app.app_context():
            web_outlook_app.init_db()
            self.previous_version = web_outlook_app.get_setting(
                web_outlook_app.LOGIN_SESSION_VERSION_SETTING_KEY,
            )
            web_outlook_app.set_setting(
                web_outlook_app.LOGIN_SESSION_VERSION_SETTING_KEY,
                web_outlook_app.DEFAULT_LOGIN_SESSION_VERSION,
            )

    def tearDown(self):
        with self.app.app_context():
            if self.previous_version is None:
                web_outlook_app.get_db().execute(
                    'DELETE FROM settings WHERE key = ?',
                    (web_outlook_app.LOGIN_SESSION_VERSION_SETTING_KEY,),
                )
            else:
                web_outlook_app.set_setting(
                    web_outlook_app.LOGIN_SESSION_VERSION_SETTING_KEY,
                    self.previous_version,
                )
            web_outlook_app.get_db().commit()
        self.app.config['TESTING'] = self.previous_testing
        if self.previous_csrf_enabled is None:
            self.app.config.pop('WTF_CSRF_ENABLED', None)
        else:
            self.app.config['WTF_CSRF_ENABLED'] = self.previous_csrf_enabled

    def oidc_config(self, client=None):
        return patch.multiple(
            web_outlook_app,
            POCKET_ID_URL='https://sso.jackyccc.com',
            POCKET_ID_CLIENT_ID='test-client-id',
            POCKET_ID_CLIENT_SECRET='test-client-secret',
            POCKET_ID_REDIRECT_URI='https://mail.example.com/auth/pocket-id/callback',
            POCKET_ID_SCOPES='openid profile email',
            pocket_id_oidc_client=client or FakePocketIdClient(),
        )

    def _login(self, client, now, duration=None):
        state = 'test-state'
        with client.session_transaction() as login_session:
            login_session['pocket_id_login_contexts'] = {
                state: {
                    'duration_days': (
                        web_outlook_app.DEFAULT_LOGIN_SESSION_DURATION_DAYS
                        if duration is None
                        else duration
                    ),
                    'next_path': '/',
                },
            }
        with self.oidc_config(), patch.object(
            web_outlook_app,
            'get_login_session_now',
            return_value=now,
        ):
            return client.get(f'/auth/pocket-id/callback?state={state}')

    def test_login_page_has_only_pocket_id_login_control(self):
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        source = response.get_data(as_text=True)

        self.assertNotIn('请输入密码登录系统', source)
        self.assertNotIn('登录密码', source)
        self.assertNotIn('type="password"', source)
        self.assertIn('action="/auth/pocket-id"', source)
        self.assertIn('>登 录</button>', source)
        self.assertEqual(self.client.post('/login', json={'password': 'anything'}).status_code, 405)

    def test_favicon_is_served_from_local_static_assets(self):
        response = self.client.get('/favicon.ico', follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content_type.startswith('image/svg+xml'))
        self.assertIn(b'<svg', response.data)
        self.assertNotIn(b'https://', response.data)

        login_source = self.client.get('/login').get_data(as_text=True)
        self.assertIn(
            '<link rel="icon" href="/favicon.ico?v=gmail-cleaner-local" type="image/svg+xml">',
            login_source,
        )

    def test_pocket_id_start_uses_configured_callback_and_duration(self):
        fake_client = FakePocketIdClient()
        with self.oidc_config(fake_client):
            response = self.client.get(
                '/auth/pocket-id?session_duration_days=90&next=/%23settings',
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].startswith('https://sso.jackyccc.com/authorize?state='))
        self.assertEqual(
            fake_client.redirect_uri,
            'https://mail.example.com/auth/pocket-id/callback',
        )
        self.assertTrue(fake_client.state)
        with self.client.session_transaction() as login_session:
            context = login_session['pocket_id_login_contexts'][fake_client.state]
            self.assertEqual(context['duration_days'], 90)
            self.assertEqual(context['next_path'], '/#settings')

    def test_missing_pocket_id_configuration_returns_to_login(self):
        with patch.multiple(
            web_outlook_app,
            POCKET_ID_CLIENT_ID='',
            pocket_id_oidc_client=None,
        ):
            response = self.client.get('/auth/pocket-id', follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/login?error=configuration'))

    def test_callback_rejects_token_response_without_id_token(self):
        state = 'missing-id-token-state'
        with self.client.session_transaction() as login_session:
            login_session['pocket_id_login_contexts'] = {
                state: {'duration_days': 30, 'next_path': '/'},
            }
        with self.oidc_config(MissingIdTokenClient()):
            response = self.client.get(
                f'/auth/pocket-id/callback?state={state}',
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers['Location'].endswith('/login?error=oidc_failed'))
        with self.client.session_transaction() as login_session:
            self.assertFalse(login_session.get('logged_in'))
            self.assertNotIn(state, login_session.get('pocket_id_login_contexts', {}))

    def test_login_options_and_default_record_absolute_expiration(self):
        now = 1_700_000_000
        expected_lifetime = 24 * 60 * 60

        for duration in web_outlook_app.LOGIN_SESSION_DURATION_OPTIONS:
            client = self.app.test_client()
            response = self._login(client, now, duration)
            self.assertEqual(response.status_code, 302)
            with client.session_transaction() as login_session:
                self.assertEqual(
                    login_session[web_outlook_app.LOGIN_SESSION_EXPIRATION_KEY],
                    now + duration * expected_lifetime,
                )
                self.assertEqual(login_session['pocket_id_subject'], 'pocket-user-123')

        default_client = self.app.test_client()
        self._login(default_client, now)
        with default_client.session_transaction() as login_session:
            self.assertEqual(
                login_session[web_outlook_app.LOGIN_SESSION_EXPIRATION_KEY],
                now + web_outlook_app.DEFAULT_LOGIN_SESSION_DURATION_DAYS * expected_lifetime,
            )

    def test_permanent_login_and_session_version_invalidation(self):
        now = 1_700_000_000
        response = self._login(
            self.client,
            now,
            web_outlook_app.LOGIN_SESSION_PERMANENT_OPTION,
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as login_session:
            self.assertEqual(
                login_session[web_outlook_app.LOGIN_SESSION_EXPIRATION_KEY],
                web_outlook_app.LOGIN_SESSION_PERMANENT_OPTION,
            )

        with self.app.app_context():
            web_outlook_app.rotate_login_session_version()
        self.assertEqual(self.client.get('/api/settings').status_code, 401)

    def test_expiration_protects_page_api_and_sse(self):
        now = 1_700_000_000
        duration = 7
        client = self.app.test_client()
        self._login(client, now, duration)

        with patch.object(
            web_outlook_app,
            'get_login_session_now',
            return_value=now + duration * 24 * 60 * 60,
        ):
            page_response = client.get('/')
            api_response = client.get('/api/settings')
            sse_response = client.get('/api/accounts/refresh-all')

        self.assertEqual(page_response.status_code, 302)
        self.assertTrue(page_response.headers['Location'].endswith('/login'))
        self.assertEqual(api_response.status_code, 401)
        self.assertTrue(api_response.get_json()['need_login'])
        self.assertEqual(sse_response.status_code, 401)

    def test_extension_login_returns_interactive_oidc_page_without_authenticating(self):
        response = self.client.post('/api/extension/login', json={
            'password': 'ignored',
            'next': '/#settings',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertTrue(payload['interactive'])
        self.assertEqual(payload['launch_url'], '/login?next=/%23settings')
        with self.client.session_transaction() as login_session:
            self.assertFalse(login_session.get('logged_in'))

    def test_login_template_remembers_duration_without_password_storage(self):
        source = (ROOT_DIR / 'templates' / 'login.html').read_text(encoding='utf-8')
        self.assertIn("const LOGIN_DURATION_STORAGE_KEY = 'outlook_login_duration_days';", source)
        self.assertIn('localStorage.getItem(LOGIN_DURATION_STORAGE_KEY)', source)
        self.assertIn('localStorage.setItem(LOGIN_DURATION_STORAGE_KEY, value)', source)
        self.assertNotRegex(source, r'localStorage\.setItem\([^)]*password')


if __name__ == '__main__':
    unittest.main()
