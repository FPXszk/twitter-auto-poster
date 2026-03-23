from __future__ import annotations

import sys
from pathlib import Path
from unittest import TestCase, main

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))

import post_quote


class PostQuoteTest(TestCase):
    def test_build_quote_reply_variables_without_reply(self) -> None:
        variables = post_quote.build_quote_reply_variables(
            "commentary",
            quote_tweet_id="12345",
        )

        self.assertEqual(variables["tweet_text"], "commentary")
        self.assertEqual(variables["attachment_url"], "https://x.com/i/status/12345")
        self.assertNotIn("reply", variables)

    def test_build_quote_reply_variables_with_reply(self) -> None:
        variables = post_quote.build_quote_reply_variables(
            "commentary",
            quote_tweet_id="12345",
            reply_to_id="67890",
        )

        self.assertEqual(
            variables["reply"],
            {
                "in_reply_to_tweet_id": "67890",
                "exclude_reply_user_ids": [],
            },
        )

    def test_extract_created_tweet_id_reads_rest_id(self) -> None:
        tweet_id = post_quote.extract_created_tweet_id(
            {
                "data": {
                    "create_tweet": {
                        "tweet_results": {
                            "result": {
                                "rest_id": "99999",
                            }
                        }
                    }
                }
            }
        )

        self.assertEqual(tweet_id, "99999")


if __name__ == "__main__":
    main()
