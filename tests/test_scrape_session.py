import unittest
from unittest.mock import patch

from scripts.scrape_session import main, OfficialRedirects, session_markdown, validate_url


URL = "https://githubuniverse.com/sessions/example"


class SessionTests(unittest.TestCase):
    def test_jsonld_session_basics(self):
        html = """
        <title>Generic site title</title>
        <script type="application/ld+json">
        {"@graph": [{"@type": "Organization", "name": "GitHub"},
          {"@type": ["Event", "Thing"], "name": "Example session",
           "description": "A session summary.",
           "performer": [{"@type": "Person", "name": "Example speaker"}],
           "startDate": "2026-10-28T10:00:00-07:00",
           "endDate": "2026-10-28T10:30:00-07:00"}]}
        </script>
        """
        result = session_markdown(html, URL)
        self.assertIn("### Example session", result)
        self.assertIn(f"[Example session]({URL})", result)
        self.assertIn("Speakers: Example speaker", result)
        self.assertIn("2026-10-28T10:00:00-07:00 – 2026-10-28T10:30:00-07:00", result)
        self.assertIn("Summary: A session summary.", result)
        self.assertIn("**Pending verification**", result)

    def test_metadata_fallback_and_markdown_escaping(self):
        html = """
        <script type="application/ld+json">invalid JSON</script>
        <meta property="og:title" content="Tools [demo]">
        <meta name="description" content="Build &amp; learn.
        &lt;script&gt;bad&lt;/script&gt;">
        """
        result = session_markdown(html, URL)
        self.assertIn(r"### Tools \[demo\]", result)
        self.assertIn(r"Build & learn. \<script\>bad\</script\>", result)
        self.assertIn("Speakers: Not provided", result)
        self.assertIn("Schedule: Not provided", result)

    def test_html_title_fallback(self):
        result = session_markdown("<title>Example &amp; tools</title>", URL)
        self.assertIn("### Example & tools", result)
        self.assertIn("Summary: Not provided", result)

    def test_single_speaker_and_event_list(self):
        html = """
        <script type="application/ld+json">
        [{"@type": "EducationEvent", "name": "Example",
          "speaker": {"name": "Example speaker"}}]
        </script>
        """
        self.assertIn("Speakers: Example speaker", session_markdown(html, URL))

    def test_missing_title(self):
        with self.assertRaisesRegex(ValueError, "No session title"):
            session_markdown("<html></html>", URL)

    def test_rejects_unofficial_urls(self):
        for url in (
            "http://githubuniverse.com/sessions/example",
            "https://githubuniverse.com.example.org/session",
            "https://reg.githubuniverse.com.example.org/session",
            "https://example.org/session",
            "https://user@githubuniverse.com/session",
            "https://githubuniverse.com:8443/session",
            "file:///etc/passwd",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)
        self.assertEqual(validate_url(URL), URL)
        registration_url = "https://reg.githubuniverse.com/flow/github/universe26/session"
        self.assertEqual(validate_url(registration_url), registration_url)

    def test_rejects_offsite_redirect(self):
        with self.assertRaises(ValueError):
            OfficialRedirects().redirect_request(
                None, None, 302, "Found", {}, "https://example.org/session"
            )

    def test_cli_reports_network_failure(self):
        with patch("sys.argv", ["scrape_session.py", URL]), patch(
            "scripts.scrape_session.build_opener"
        ) as opener, patch("sys.stderr") as stderr:
            opener.return_value.open.side_effect = OSError("offline")
            self.assertEqual(main(), 1)
            self.assertIn("offline", stderr.write.call_args_list[0].args[0])


if __name__ == "__main__":
    unittest.main()
