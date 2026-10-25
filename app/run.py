import sys
import os

# Redirect to code.main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from code.main import main

if __name__ == "__main__":
    main()
