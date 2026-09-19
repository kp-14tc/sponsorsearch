import sys
from healthcheck import main

if __name__ == '__main__':
    sys.argv.extend(['--service', 'searxng'])
    sys.exit(main())
