    def switch(self, branch_name):
        """Switch to a branch and update the working directory to match its latest commit."""
        # 1. Verify the branch exists
        branch_file = os.path.join(self.heads_dir, branch_name)
        if not os.path.exists(branch_file):
            raise Exception(f"Branch '{branch_name}' does not exist")

        # 2. Get the commit hash of the target branch
        with open(branch_file, "r") as f:
            commit_hash = f.read().strip()
        if not commit_hash:
            raise Exception(f"Branch '{branch_name}' has no commits")

        # 3. Read the commit object and its tree
        commit_obj = self._read_object(commit_hash)
        if not commit_obj or 'tree' not in commit_obj:
            raise Exception("Invalid commit object")
        tree_hash = commit_obj['tree']
        tree_obj = self._read_object(tree_hash)
        if not tree_obj:
            raise Exception("Tree object not found")

        # 4. Restore all tracked files from the tree
        for file_path, file_hash in tree_obj.items():
            full_path = os.path.join(self.repo_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            blob_data = self._read_object(file_hash)
            if blob_data and isinstance(blob_data, bytes):
                with open(full_path, 'wb') as f:
                    f.write(blob_data)
            else:
                # If it's a nested tree, you'd handle recursively; for flat structure just skip
                pass

        # 5. Remove files that exist in the working directory but are NOT in the tree
        #    (i.e., files that are untracked or were deleted in this branch)
        tracked_files = set(tree_obj.keys())
        for root, dirs, files in os.walk(self.repo_path):
            # Skip .tvc and virtual environment
            if '.tvc' in dirs:
                dirs.remove('.tvc')
            if 'dstreet' in dirs:
                dirs.remove('dstreet')
            rel_root = os.path.relpath(root, self.repo_path)
            if rel_root == '.':
                rel_root = ''
            for f in files:
                full_rel = os.path.join(rel_root, f) if rel_root else f
                if full_rel not in tracked_files:
                    os.remove(os.path.join(root, f))
                    print(f"Removed untracked file: {full_rel}")

        # 6. Update HEAD to point to the new branch
        with open(self.head_file, "w") as f:
            f.write(f"ref: refs/heads/{branch_name}\n")

        print(f"Switched to branch '{branch_name}' (commit {commit_hash[:8]})")