#!/usr/bin/env python3
"""
tvc - Decentralized Version Control CLI
Unified version with all commands (init, commit, log, diff, branch, switch, merge, status, proof, clone, shelf, unshelf)
"""

import argparse
import sys
import os
import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from tvc.tvc_system import TVCSystem

# ANSI colors
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
RESET = '\033[0m'

WELCOME_MESSAGE = """
╔══════════════════════════════════════════════════════════════════╗
║                     🚀 TVC - Decentralized VCS                   ║
║         Proof-of-Development · Git‑less · AI‑ready               ║
╚══════════════════════════════════════════════════════════════════╝

✨ Welcome to TVC – your decentralized version control system.

📌 Basic commands:
   tvc init                    – Initialize a new repository
   tvc commit -m "message"     – Record changes with proof of development
   tvc log                     – View commit history
   tvc diff <commit1> <commit2>– Show changes between commits
   tvc branch <name>           – Create a new branch
   tvc switch <branch>         – Switch branches (alias: checkout)
   tvc merge <branch>          – Fast‑forward merge another branch
   tvc status                  – Show working tree status
   tvc proof <commit>          – Show contribution proof (score, metrics)
   tvc clone <url>             – Clone a repository from a remote peer
   tvc shelf                   – Save untracked files temporarily
   tvc unshelf                 – Restore previously shelved files

🤖 AI‑assisted commits:
   tvc commit --ai --conversation-ids "id1 id2" -m "AI‑generated code"

📚 Full documentation: docs/developer/TVC_SETUP_GUIDE.md

💡 First commit may take 20‑60 seconds (scanning files). 
   Use .tvcignore to exclude large folders.

Happy coding! 🎨
"""

# ---------- Helper functions ----------
def resolve_commit(tvc, commit_spec):
    """Resolve HEAD or short hash to full commit key."""
    if commit_spec == 'HEAD':
        branch_ref = tvc._get_current_branch()
        commit_hash = tvc._get_branch_commit(branch_ref)
        if not commit_hash:
            print("❌ No commits on current branch")
            sys.exit(1)
        return commit_hash
    # If it's already a full key (starts with 'commit:' and length > 20), return as is
    if commit_spec.startswith('commit:') and len(commit_spec) > 20:
        return commit_spec
    # Expand short hash (e.g., 'commit:e' or just 'e')
    short = commit_spec.replace('commit:', '')
    matches = list(Path('.tvc/objects').glob(f'commit_{short}*'))
    if not matches:
        print(f"❌ No commit matching '{commit_spec}' found")
        sys.exit(1)
    if len(matches) > 1:
        print(f"❌ Multiple matches for '{commit_spec}': {[m.name[7:] for m in matches]}")
        sys.exit(1)
    full_hash = matches[0].name[7:]  # remove 'commit_'
    return f'commit:{full_hash}'

# ---------- Command implementations ----------
def cmd_diff(args):
    tvc = TVCSystem()
    c1 = resolve_commit(tvc, args.commit1)
    c2 = resolve_commit(tvc, args.commit2)

    commit1_data = tvc.storage.load_object(c1)
    commit2_data = tvc.storage.load_object(c2)
    if not commit1_data:
        print(f"❌ Commit {c1[:8] if c1 else c1} not found")
        return
    if not commit2_data:
        print(f"❌ Commit {c2[:8] if c2 else c2} not found")
        return

    tree1 = commit1_data.get('tree_hash')
    tree2 = commit2_data.get('tree_hash')

    added, modified, removed = tvc._get_changed_files(tree1, tree2)

    print(f"Diff between {c1[:8]} and {c2[:8]}")
    print(f"Added: {len(added)}, Modified: {len(modified)}, Removed: {len(removed)}\n")

    for f in added:
        print(f"{GREEN}+ {f}{RESET}")
    for f in modified:
        print(f"{YELLOW}~ {f}{RESET}")
    for f in removed:
        print(f"{RED}- {f}{RESET}")

    if tree1 and tree2:
        all_files = added + modified + removed
        stats = tvc._compute_diff_stats(tree1, tree2, all_files)
        print(f"\nLines added: {stats['lines_added']}, removed: {stats['lines_removed']}")
        print(f"Complexity delta: {stats['complexity_delta']}")
    else:
        if tree1:
            total_lines = tvc._compute_full_line_count(tree2)['lines_added']
            print(f"\nLines added: {total_lines}, removed: 0")
        elif tree2:
            total_lines = tvc._compute_full_line_count(tree2)['lines_added']
            print(f"\nLines added: {total_lines}, removed: 0")

def cmd_log(args):
    tvc = TVCSystem()
    tvc.log(max_count=args.max_count)

def cmd_merge(args):
    tvc = TVCSystem()
    current_branch_ref = tvc._get_current_branch()
    current_commit = tvc._get_branch_commit(current_branch_ref)
    if not current_commit:
        print("❌ No commits on current branch")
        return

    target_branch_ref = f"refs/heads/{args.branch}"
    target_commit = tvc._get_branch_commit(target_branch_ref)
    if not target_commit:
        print(f"❌ Branch '{args.branch}' not found")
        return

    def is_ancestor(ancestor, descendant):
        while descendant:
            if descendant == ancestor:
                return True
            data = tvc.storage.load_object(descendant)
            parents = data.get('parents', [])
            descendant = parents[0] if parents else None
        return False

    if is_ancestor(current_commit, target_commit):
        # Fast‑forward: move current branch pointer to target commit
        tvc._update_branch(current_branch_ref, target_commit)
        tvc.checkout(args.branch)   # update working directory
        print(f"✅ Fast‑forward merged '{args.branch}' into current branch.")
    else:
        print("❌ Not a fast‑forward merge. Manual conflict resolution required.")
        print("Use `tvc diff` to see differences and `tvc switch` to apply changes.")

def cmd_clone(args):
    """Clone a repository from a remote peer."""
    remote_url = args.url.rstrip('/')
    branch = args.branch
    print(f"Cloning from {remote_url} (branch: {branch})...")
    
    # Fetch remote heads
    try:
        resp = requests.get(f"{remote_url}/tvc/heads", timeout=10)
        if resp.status_code != 200:
            print(f"❌ Failed to fetch heads from {remote_url}")
            return
        heads = resp.json()
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return
    
    if branch not in heads:
        print(f"❌ Branch '{branch}' not found on remote. Available: {list(heads.keys())}")
        return
    commit_hash = heads[branch]
    
    # Create local .tvc directory
    tvc = TVCSystem()  # creates .tvc/ in current dir
    print("Fetching objects...")
    
    # Helper to fetch a single object
    def fetch_object(key):
        try:
            resp = requests.get(f"{remote_url}/tvc/objects/{key}", timeout=10)
            if resp.status_code == 200:
                obj_path = tvc.storage.repo_path / "objects" / key.replace(":", "_")
                obj_path.write_bytes(resp.content)
                return True
        except Exception:
            pass
        return False
    
    # Recursively fetch commit and its tree
    stack = [commit_hash]
    fetched = set()
    while stack:
        key = stack.pop()
        if key in fetched:
            continue
        if fetch_object(key):
            fetched.add(key)
            data = tvc.storage.load_object(key)
            if data and 'tree_hash' in data:
                # Fetch tree
                tree_key = data['tree_hash']
                if tree_key not in fetched:
                    stack.append(tree_key)
                # Fetch parent commits
                for parent in data.get('parents', []):
                    if parent not in fetched:
                        stack.append(parent)
            elif data and 'entries' in data:
                # This is a tree object: fetch all blob/tree children
                for entry in data.get('entries', []):
                    child_key = entry['hash']
                    if child_key not in fetched:
                        stack.append(child_key)
        else:
            print(f"⚠️ Failed to fetch {key}")
    
    # Set up branch ref
    tvc._update_branch(f"refs/heads/{branch}", commit_hash)
    head_file = tvc.tvc_dir / "HEAD"
    head_file.write_text(f"ref: refs/heads/{branch}\n")
    
    # Checkout the branch to restore working directory
    tvc.checkout(branch)
    print(f"✅ Cloned repository from {remote_url} (branch: {branch})")

def cmd_shelf(args):
    """Move untracked files to a shelf (temporary storage)."""
    tvc = TVCSystem()
    shelf_dir = tvc.tvc_dir / "shelf"
    shelf_dir.mkdir(exist_ok=True)
    
    # Get untracked files (simplified: files not in index.json)
    index_file = tvc.tvc_dir / "index.json"
    tracked = set()
    if index_file.exists():
        index = json.loads(index_file.read_text())
        for rel in index.get('files', {}):
            tracked.add(rel)
    
    untracked = []
    for root, dirs, files in os.walk(tvc.repo_root):
        # Skip .tvc directory
        if Path(root) == tvc.tvc_dir:
            continue
        rel_root = Path(root).relative_to(tvc.repo_root)
        for f in files:
            rel = str(rel_root / f) if rel_root != Path('.') else f
            if rel not in tracked and not tvc._is_ignored(rel):
                untracked.append(rel)
    
    if not untracked:
        print("No untracked files to shelf.")
        return
    
    moved = 0
    for rel in untracked:
        src = tvc.repo_root / rel
        dst = shelf_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        moved += 1
    print(f"Shelved {moved} files. Use 'tvc unshelf' to restore.")

def cmd_unshelf(args):
    """Restore previously shelved files."""
    tvc = TVCSystem()
    shelf_dir = tvc.tvc_dir / "shelf"
    if not shelf_dir.exists():
        print("No shelved files found.")
        return
    
    restored = 0
    for root, dirs, files in os.walk(shelf_dir):
        for f in files:
            src = Path(root) / f
            rel = src.relative_to(shelf_dir)
            dst = tvc.repo_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            restored += 1
    
    # Remove empty directories
    shutil.rmtree(shelf_dir, ignore_errors=True)
    print(f"Restored {restored} files from shelf.")

# ---------- Main CLI ----------
def main():
    parser = argparse.ArgumentParser(description="tvc - Decentralized Version Control", prog="tvc")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    subparsers.add_parser("init", help="Initialize empty tvc repository")

    # commit
    p_commit = subparsers.add_parser("commit", help="Record changes")
    p_commit.add_argument("-m", "--message", required=True)
    p_commit.add_argument("--author", default="unknown")
    p_commit.add_argument("--ai", action="store_true")
    p_commit.add_argument("--conversation-ids", nargs="+")

    # log
    p_log = subparsers.add_parser("log", help="Show commit history")
    p_log.add_argument("-n", "--max-count", type=int, default=10, help="Number of commits to show")

    # diff
    p_diff = subparsers.add_parser("diff", help="Show diff between two commits")
    p_diff.add_argument("commit1", help="First commit (hash or HEAD)")
    p_diff.add_argument("commit2", help="Second commit (hash or HEAD)")
    p_diff.add_argument("--files", nargs="*", help="Limit to specific files (not yet implemented)")

    # branch
    p_branch = subparsers.add_parser("branch", help="List or create branches")
    p_branch.add_argument("name", nargs="?")

    # switch (main command for branch switching)
    p_switch = subparsers.add_parser("switch", help="Switch branches")
    p_switch.add_argument("branch")

    # checkout (alias for switch)
    p_checkout = subparsers.add_parser("checkout", help="Switch branches (alias for switch)")
    p_checkout.add_argument("branch")

    # merge
    p_merge = subparsers.add_parser("merge", help="Fast‑forward merge another branch")
    p_merge.add_argument("branch")

    # status
    subparsers.add_parser("status", help="Working tree status")

    # proof
    p_proof = subparsers.add_parser("proof", help="Show proof for commit")
    p_proof.add_argument("commit_hash", help="Commit hash (full or short)")

    # clone
    p_clone = subparsers.add_parser("clone", help="Clone a repository from a remote peer")
    p_clone.add_argument("url", help="Remote peer URL (e.g., http://localhost:5000)")
    p_clone.add_argument("--branch", default="main", help="Branch to checkout (default: main)")

    # shelf / unshelf
    subparsers.add_parser("shelf", help="Save untracked files temporarily")
    subparsers.add_parser("unshelf", help="Restore previously shelved files")

    # Show help if no args
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Handle init (doesn't require .tvc)
    if args.command == "init":
        tvc = TVCSystem()
        tvc._init_refs()
        print("✅ Initialized empty tvc repository in .tvc/")
        return

    # All other commands require an existing .tvc directory
    if not (Path.cwd() / ".tvc").exists():
        print("❌ Not a tvc repository. Run 'tvc init' first.")
        sys.exit(1)

    tvc = TVCSystem()

    if args.command == "commit":
        tvc.commit(args.message, args.author, args.ai, args.conversation_ids or [])
    elif args.command == "log":
        cmd_log(args)
    elif args.command == "diff":
        cmd_diff(args)
    elif args.command == "branch":
        tvc.branch(args.name)
    elif args.command == "switch":
        tvc.checkout(args.branch)
    elif args.command == "checkout":
        tvc.checkout(args.branch)
    elif args.command == "merge":
        cmd_merge(args)
    elif args.command == "status":
        tvc.status()
    elif args.command == "proof":
        full_hash = resolve_commit(tvc, args.commit_hash)
        tvc.show_proof(full_hash)
    elif args.command == "clone":
        cmd_clone(args)
    elif args.command == "shelf":
        cmd_shelf(args)
    elif args.command == "unshelf":
        cmd_unshelf(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()