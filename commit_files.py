import sys
sys.path.insert(0, '.')
from tvc.tvc_system import TVCSystem
tvc = TVCSystem('.')
if len(sys.argv) < 4:
    print("Usage: python3 commit_files.py <message> <author> <file1> [file2 ...]")
    sys.exit(1)
tvc.commit(message=sys.argv[1], author=sys.argv[2], files=sys.argv[3:])
