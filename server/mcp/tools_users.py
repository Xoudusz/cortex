#!/usr/bin/env python3
"""Multi-user MCP tools: whoami (everyone) + user/workspace/repo management (admin only, see tools.ADMIN_TOOLS)."""

from config import BASE_URL
import oauth as _oauth
import users as _users
from state import current_user, get_active_workspace
from repos import _load_repos, _save_repos, ensure_workspace_repos


def _invite_link(token: str) -> str:
    return f"{BASE_URL}/invite/{token}"


def register_users(mcp) -> None:
    @mcp.tool()
    def whoami() -> str:
        """Show who you are logged in as, your active workspace, and the workspaces you can use."""
        user = current_user() or _users.ADMIN
        wss = _users.user_workspaces(user)
        try:
            active = get_active_workspace()
        except PermissionError:
            active = "none"
        role = "admin" if _users.is_admin(user) else "member"
        return (f"User: {user} ({role})\nActive workspace: {active}\n"
                f"Workspaces: {', '.join(wss) if wss else 'none — ask the admin to grant one'}")

    @mcp.tool()
    def create_workspace(name: str, wiki_repo: str = "") -> str:
        """[admin] Create a shared workspace (own code + notes index) that users can be granted.

        wiki_repo: optional "owner/name" GitHub repo of markdown files used as the workspace's notes
        (the project wiki). Your private vault stays in 'default' and is never shared.
        Add code repos afterwards with add_repo(repo, workspace).
        """
        err = _users.create_workspace(name, wiki_repo)
        if err:
            return err
        ensure_workspace_repos(name.strip().lower())
        wiki = f" Notes come from {wiki_repo}." if wiki_repo else " No wiki repo: notes stay empty."
        return f"Workspace '{name}' created.{wiki} Next: add_repo(repo, '{name}'), then invite_user()."

    @mcp.tool()
    def delete_workspace(name: str) -> str:
        """[admin] Unregister a shared workspace and remove it from every user. Indexed data stays on disk."""
        return _users.delete_workspace(name) or f"Workspace '{name}' deleted (access removed for all users)."

    @mcp.tool()
    def set_workspace_wiki(name: str, wiki_repo: str) -> str:
        """[admin] Set (or clear with "") the markdown wiki repo used as a workspace's notes."""
        return _users.set_wiki(name, wiki_repo) or (
            f"Wiki for '{name}' set to {wiki_repo or 'none'}. Run reindex(notes=True, code=False) in that workspace.")

    @mcp.tool()
    def add_repo(repo: str, workspace: str) -> str:
        """[admin] Track a GitHub repo ("owner/name") in a workspace's code index. Reindex afterwards."""
        if not _users.valid_repo(repo):
            return "repo must be in owner/name format."
        if workspace != _users.DEFAULT_WS and workspace not in _users.list_registered():
            return f"Unknown workspace '{workspace}'."
        repos = _load_repos(workspace)
        if repo in repos:
            return f"{repo} is already tracked in '{workspace}'."
        _save_repos(repos + [repo], workspace)
        return f"Added {repo} to '{workspace}'. Run reindex(code=True, repo='{repo.split('/')[1]}') there."

    @mcp.tool()
    def remove_repo(repo: str, workspace: str) -> str:
        """[admin] Stop tracking a repo in a workspace (its chunks are removed on the next full code reindex)."""
        repos = _load_repos(workspace)
        if repo not in repos:
            return f"{repo} is not tracked in '{workspace}'."
        _save_repos([r for r in repos if r != repo], workspace)
        return f"Removed {repo} from '{workspace}'."

    @mcp.tool()
    def invite_user(username: str, workspaces: list[str]) -> str:
        """[admin] Create a single-use invite link (valid 7 days) for a new user with access to workspaces.

        Send the link to the person; they choose their own password. The link is shown only once.
        """
        token, err = _users.create_invite(username, workspaces, created_by=current_user() or _users.ADMIN)
        if err:
            return err
        return (f"Invite for '{username}' ({', '.join(workspaces) or 'no workspaces'}), valid 7 days, single use:\n"
                f"{_invite_link(token)}")

    @mcp.tool()
    def list_users() -> str:
        """[admin] List users, their workspaces, and pending invites."""
        lines = ["Users:"]
        for u in _users.list_users():
            lines.append(f"  {u['username']}{' (admin)' if u['admin'] else ''}: {', '.join(u['workspaces']) or '-'}")
        invites = _users.list_invites()
        if invites:
            lines.append("Pending invites:")
            lines += [f"  {i['username']}: {', '.join(i['workspaces']) or '-'} (expires {i['expires_at'][:10]})"
                      for i in invites]
        regs = _users.list_registered()
        lines.append("Shared workspaces: " + (", ".join(
            f"{n}{' (wiki ' + w['wiki_repo'] + ')' if w.get('wiki_repo') else ''}" for n, w in sorted(regs.items()))
            or "none"))
        return "\n".join(lines)

    @mcp.tool()
    def remove_user(username: str) -> str:
        """[admin] Delete a user (or a pending invite) and revoke all of their logins immediately."""
        if username == _users.ADMIN:
            return "The admin can't be removed."
        removed = _users.remove_user(username)
        invite = _users.revoke_invite(username)
        n = _oauth.revoke_user_tokens(username)
        if not removed and not invite:
            return f"No user or invite named '{username}'."
        return f"Removed '{username}' ({n} active login(s) revoked)."

    @mcp.tool()
    def grant_workspace(username: str, workspace: str) -> str:
        """[admin] Give an existing user access to a shared workspace."""
        return _users.grant(username, workspace) or f"'{username}' can now use '{workspace}'."

    @mcp.tool()
    def revoke_workspace(username: str, workspace: str) -> str:
        """[admin] Remove a user's access to a workspace (takes effect on their next tool call)."""
        return _users.revoke(username, workspace) or f"'{username}' no longer has '{workspace}'."
