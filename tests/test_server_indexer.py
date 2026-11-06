"""Server indexer helpers — no network, no Qdrant."""

import os
import sys

sys.path[:0] = [os.path.join(os.path.dirname(__file__), "..", "server", "indexer"),
                os.path.join(os.path.dirname(__file__), "..", "core")]
os.environ["GITHUB_TOKEN"] = "ghp_secret123"

import index_code  # noqa: E402

index_code.TOKEN = "ghp_secret123"


def test_git_error_masks_token_and_hints_auth():
    err = ("Cloning into '/tmp/repos/x'...\n"
           "remote: Invalid username or token.\n"
           "fatal: Authentication failed for 'https://Xoudusz:ghp_secret123@github.com/a/b.git/'\n")
    msg = index_code.git_error(err)
    assert "ghp_secret123" not in msg and "***" in msg
    assert "Authentication failed" in msg and "hint: GitHub token" in msg


def test_git_error_repo_not_found_hint():
    msg = index_code.git_error("remote: Repository not found.\nfatal: repository 'https://x' not found\n")
    assert "classic PAT" in msg


def test_git_error_empty():
    assert index_code.git_error("") == "git printed no error"


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print(f"  ok  {t.__name__}")
        except Exception:
            failed += 1; print(f"  FAIL {t.__name__}"); traceback.print_exc()
    print(f"\n{len(tests) - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
