from __future__ import annotations

import os
import pickle
from typing import Any, Dict, Iterable, Optional
from webdriver_manager.chrome import ChromeDriverManager
from requests import Session

from fantasy_config import (
    FANTRAX_LEAGUE_ID,
    FANTRAX_USERNAME,
    FANTRAX_PASSWORD,
)


class FantraxClient:
    """
    Minimal client scaffold around fantraxapi.League.

    - Reads league and credentials from fantasy_config
    - Supports cookie-based login for private endpoints (optional)
    - Exposes a few convenience methods for common league data
    """

    def __init__(
        self,
        league_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        cookie_filepath: str = "fantraxloggedin.cookie",
        auto_login: bool = False,
    ) -> None:
        import fantraxapi

        self.league_id = league_id or FANTRAX_LEAGUE_ID
        self.username = username or FANTRAX_USERNAME
        self.password = password or FANTRAX_PASSWORD
        self.cookie_filepath = cookie_filepath

        self._fantraxapi = fantraxapi
        
        # Install cookie login hook early if requested so constructor requests are wrapped
        if auto_login:
            self.enable_cookie_login()

        # Construct League; if NotLoggedIn is raised, force fresh cookie and retry
        try:
            self._league = fantraxapi.League(self.league_id)
        except Exception as exc:
            # Only handle NotLoggedIn here; re-raise other exceptions
            not_logged_in_cls = getattr(fantraxapi, "NotLoggedIn", None)
            if not_logged_in_cls is not None and isinstance(exc, not_logged_in_cls):
                from requests import Session as _Session
                # Persist a fresh cookie to disk and retry constructing the League
                self._add_cookie_to_session(_Session(), ignore_cookie=True)
                self._league = fantraxapi.League(self.league_id)
            else:
                raise

    # -------------------- Auth / Cookie Login --------------------
    def enable_cookie_login(self) -> None:
        """
        Monkey-patch fantraxapi.api.request to auto-inject cookies for
        private endpoints, as shown in the official docs.
        """
        from fantraxapi import api, NotLoggedIn
        from fantraxapi.api import Method

        old_request = api.request

        def new_request(league: "Any", methods: Iterable[Method] | Method) -> Dict[str, Any]:
            try:
                if not getattr(league, "logged_in", False):
                    self._add_cookie_to_session(league.session)
                return old_request(league, methods)
            except NotLoggedIn:
                # One retry only to avoid infinite loops
                self._add_cookie_to_session(league.session, ignore_cookie=True)
                return old_request(league, methods)

        api.request = new_request  # type: ignore[assignment]

    def refresh_login(self, ignore_saved_cookie: bool = False) -> None:
        """Force-load cookies into the current session."""
        self._add_cookie_to_session(self._league.session, ignore_cookie=ignore_saved_cookie)

    def _add_cookie_to_session(self, session: Session, ignore_cookie: bool = False) -> None:
        # Reuse saved cookie if available
        if not ignore_cookie and os.path.exists(self.cookie_filepath):
            with open(self.cookie_filepath, "rb") as f:
                saved = pickle.load(f)
                for cookie in saved:
                    session.cookies.set(
                        cookie["name"],
                        cookie["value"],
                        domain=cookie.get("domain"),
                        path=cookie.get("path", "/"),
                    )  # type: ignore[index]
            return

        # Try loading cookies from installed browsers to avoid Selenium
        try:
            import browser_cookie3  # type: ignore
            # Attempt common browsers; they may raise if not installed/accessible
            for loader in (
                getattr(browser_cookie3, "chrome", None),
                getattr(browser_cookie3, "edge", None),
                getattr(browser_cookie3, "firefox", None),
            ):
                if loader is None:
                    continue
                try:
                    jar = loader(domain_name="fantrax.com")  # type: ignore[operator]
                    # Preserve domains/paths by updating the cookie jar directly
                    session.cookies.update(jar)  # type: ignore[arg-type]
                    # If we got anything for fantrax, accept it
                    if len(jar) > 0:  # type: ignore[arg-type]
                        return
                except Exception:
                    continue
        except Exception:
            # browser_cookie3 not available or failed; continue to Selenium
            pass

        # Headless login using Selenium to persist a fresh cookie
        # Only import heavy deps when needed
        from selenium import webdriver
        from selenium.webdriver import Keys
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions
        from selenium.webdriver.support.ui import WebDriverWait
        service = Service(ChromeDriverManager().install())

        def perform_login(headless: bool = True) -> bool:
            # Build fresh options per attempt
            opts = Options()
            if headless:
                opts.add_argument("--headless=new")
                opts.add_argument("--window-size=1920,1600")
            else:
                opts.add_argument("--window-size=1280,900")
            opts.add_argument("--ignore-certificate-errors")
            opts.add_argument("--allow-insecure-localhost")
            opts.add_argument("--proxy-server=direct://")
            opts.add_argument("--proxy-bypass-list=*")
            opts.add_argument("--disable-gpu")
            ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
            opts.add_argument(f"user-agent={ua}")
            try:
                opts.set_capability("acceptInsecureCerts", True)
            except Exception:
                pass

            # Reuse existing Chrome profile if available (avoids login form and TLS quirks)
            try:
                user_data_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
                if user_data_dir and os.path.isdir(user_data_dir):
                    opts.add_argument(f"--user-data-dir={user_data_dir}")
                    opts.add_argument("--profile-directory=Default")
            except Exception:
                pass

            with webdriver.Chrome(service=service, options=opts) as driver:
                driver.get("https://www.fantrax.com/login")
                username_box = WebDriverWait(driver, 30).until(
                    expected_conditions.presence_of_element_located((By.XPATH, "//input[@formcontrolname='email']"))
                )
                username_box.send_keys(self.username)

                password_box = WebDriverWait(driver, 30).until(
                    expected_conditions.presence_of_element_located((By.XPATH, "//input[@formcontrolname='password']"))
                )
                password_box.send_keys(self.password)
                password_box.send_keys(Keys.ENTER)

                WebDriverWait(driver, 45).until(lambda d: len(d.get_cookies()) > 0)
                cookies = driver.get_cookies()
                with open(self.cookie_filepath, "wb") as cookie_file:
                    pickle.dump(cookies, cookie_file)
                for cookie in cookies:
                    session.cookies.set(
                        cookie["name"],
                        cookie["value"],
                        domain=cookie.get("domain"),
                        path=cookie.get("path", "/"),
                    )  # type: ignore[index]
                # Align session UA with browser UA
                try:
                    session.headers.update({"User-Agent": ua})
                except Exception:
                    pass
                return True

        # Try headless first, then non-headless as a fallback to bypass COM/TLS quirks
        try:
            if perform_login(headless=True):
                return
        except Exception:
            pass
        # Retry without headless to improve compatibility
        if perform_login(headless=False):
            return

    # -------------------- Exposed League Methods --------------------
    @property
    def league(self):
        return self._league

    def scoring_periods(self) -> Dict[str, Any]:
        return self._league.scoring_periods()

    def teams(self) -> Dict[str, Any]:
        return self._league.teams()

    def standings(self) -> Dict[str, Any]:
        return self._league.standings()

    def trade_block(self) -> Dict[str, Any]:
        """Private endpoint; requires cookie login."""
        return self._league.trade_block()

    def transactions(self) -> Dict[str, Any]:
        return self._league.transactions()

    # -------------------- Convenience --------------------
    @classmethod
    def default(cls) -> "FantraxClient":
        """Construct with config values and no auto-login by default."""
        return cls()


__all__ = ["FantraxClient"]


