import os
import json
import hashlib
from datetime import datetime

class TVCSystem:
    def __init__(self, repo_path="."):
        self.repo_path = os.path.abspath(repo_path)
        self.tvc_dir = os.path.join(self.repo_path, ".tvc")
        self.objects_dir = os.path.join(self.tvc_dir, "objects")
        self.refs_dir = os.path.join(self.tvc_dir, "refs")
        self.heads_dir = os.path.join(self.refs_dir, "heads")
        self.head_file = os.path.join(self.tvc_dir, "HEAD")

    def _ensure_dirs(self):
        os.makedirs(self.objects_dir, exist_ok=True)
        os.makedirs(self.heads_dir, exist_ok=True)

    def _init_refs(self):
        self._ensure_dirs()
        if not os.path.exists(self.head_file):
            with open(self.head_file, "w") as f:
                f.write("ref: refs/heads/main\n")
        main_branch = os.path.join(self.heads_dir, "main")
        if not os.path.exists(main_branch):
            with open(main_branch, "w") as f:
                pass

    def init(self):
        if os.path.exists(self.tvc_dir) and os.listdir(self.tvc_dir):
            raise Exception("Repository already exists")
        self._ensure_dirs()
        self._init_refs()
        print(f"Initialized empty TVC repository in {self.tvc_dir}")

    def _hash_object(self, data):
        sha1 = hashlib.sha1(data).hexdigest()
        dirname = sha1[:2]
        filename = sha1[2:]
        obj_path = os.path.join(self.objects_dir, dirname)
        os.makedirs(obj_path, exist_ok=True)
        with open(os.path.join(obj_path, filename), "wb") as f:
            f.write(data)
        return sha1

    def _get_current_branch(self):
        if not os.path.exists(self.head_file):
            return None
        with open(self.head_file, "r") as f:
            ref = f.read().strip()
        if ref.startswith("ref: refs/heads/"):
            return ref.replace("ref: refs/heads/", "")
        return None

    def _update_branch_ref(self, branch, commit_hash):
        branch_file = os.path.join(self.heads_dir, branch)
        with open(branch_file, "w") as f:
            f.write(commit_hash + "\n")

    def _get_head_commit(self):
        current_branch = self._get_current_branch()
        if not current_branch:
            if os.path.exists(self.head_file):
                with open(self.head_file, "r") as f:
                    head_content = f.read().strip()
                    if not head_content.startswith("ref:"):
                        return head_content
            return None
        branch_file = os.path.join(self.heads_dir, current_branch)
        if not os.path.exists(branch_file):
            return None
        with open(branch_file, "r") as f:
            commit_hash = f.read().strip()
            return commit_hash if commit_hash else None

    def commit(self, message, author, files=None, ai=False, conversation_ids=None):
        self._ensure_dirs()
        if not files:
            print("Nothing to commit. Specify files.")
            return None
        tree_data = {}
        for f in files:
            fpath = os.path.join(self.repo_path, f)
            if not os.path.exists(fpath):
                continue
            with open(fpath, "rb") as fp:
                file_hash = self._hash_object(fp.read())
            tree_data[f] = file_hash
        tree_content = json.dumps(tree_data, sort_keys=True).encode()
        tree_hash = self._hash_object(tree_content)
        commit_obj = {
            "tree": tree_hash,
            "parent": self._get_head_commit(),
            "author": author,
            "timestamp": datetime.now().isoformat(),
            "message": message,
        }
        commit_data = json.dumps(commit_obj, indent=2).encode()
        commit_hash = self._hash_object(commit_data)
        current_branch = self._get_current_branch()
        if current_branch:
            self._update_branch_ref(current_branch, commit_hash)
        else:
            with open(self.head_file, "w") as f:
                f.write(commit_hash)
        print(f"Committed as {commit_hash}")
        return commit_hash

    def branch(self, name=None):
        self._ensure_dirs()
        if name is None:
            branches = [b for b in os.listdir(self.heads_dir)]
            current = self._get_current_branch()
            for b in sorted(branches):
                if b == current:
                    print(f"* {b}")
                else:
                    print(f"  {b}")
            return
        head_commit = self._get_head_commit()
        if not head_commit:
            raise Exception("Cannot create branch without any commits")
        branch_file = os.path.join(self.heads_dir, name)
        if os.path.exists(branch_file):
            raise Exception(f"Branch '{name}' already exists")
        with open(branch_file, "w") as f:
            f.write(head_commit + "\n")
        print(f"Created branch '{name}'")

    def switch(self, branch_name):
        self._ensure_dirs()
        branch_file = os.path.join(self.heads_dir, branch_name)
        if not os.path.exists(branch_file):
            raise Exception(f"Branch '{branch_name}' does not exist")
        with open(self.head_file, "w") as f:
            f.write(f"ref: refs/heads/{branch_name}\n")
        print(f"Switched to branch '{branch_name}'")

    def checkout(self, branch_name):
        self.switch(branch_name)

    def status(self):
        self._ensure_dirs()
        head_commit = self._get_head_commit()
        tracked = set()
        if head_commit:
            commit_obj = self._read_object(head_commit)
            if commit_obj and "tree" in commit_obj:
                tree_obj = self._read_object(commit_obj["tree"])
                if tree_obj:
                    tracked = set(tree_obj.keys())
        all_files = set()
        for root, dirs, files in os.walk(self.repo_path):
            rel_root = os.path.relpath(root, self.repo_path)
            if rel_root == ".":
                rel_root = ""
            if ".tvc" in dirs:
                dirs.remove(".tvc")
            if "dstreet" in dirs:
                dirs.remove("dstreet")
            if "__pycache__" in dirs:
                dirs.remove("__pycache__")
            if "toonedoutframes.egg-info" in dirs:
                dirs.remove("toonedoutframes.egg-info")
            for f in files:
                if f.endswith(".pyc"):
                    continue
                if rel_root:
                    all_files.add(os.path.join(rel_root, f))
                else:
                    all_files.add(f)
        untracked = all_files - tracked
        if untracked:
            print("Untracked files:")
            for f in sorted(untracked):
                print(f"  {f}")
        else:
            print("Working tree clean")

    def log(self, max_count: int = 10):
        """Show commit history of current branch."""
        self._ensure_dirs()
        commit_hash = self._get_head_commit()
        if not commit_hash:
            print("No commits yet")
            return
        count = 0
        while commit_hash and count < max_count:
            commit_obj = self._read_object(commit_hash)
            if not commit_obj:
                break
            print(f"commit {commit_hash}")
            print(f"Author: {commit_obj.get('author', 'unknown')}")
            print(f"Date: {commit_obj.get('timestamp', 'unknown')}")
            print(f"\n    {commit_obj.get('message', '')}\n")
            commit_hash = commit_obj.get('parent')
            count += 1

    def _read_object(self, sha1):
        obj_path = os.path.join(self.objects_dir, sha1[:2], sha1[2:])
        if not os.path.exists(obj_path):
            return None
        with open(obj_path, "rb") as f:
            data = f.read()
        try:
            return json.loads(data.decode())
        except:
            return None

    # Stubs for other commands
    def diff(self, commit1, commit2): print("diff not implemented")
    def merge(self, branch): print("merge not implemented")
    def proof(self, commit): print("proof not implemented")
    def clone(self, remote): print("clone not implemented")
    def shelf(self): print("shelf not implemented")
    def unshelf(self): print("unshelf not implemented")
