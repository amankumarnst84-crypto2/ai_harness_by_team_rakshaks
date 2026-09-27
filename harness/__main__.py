import sys

if len(sys.argv) > 1 and sys.argv[1] == "chat":
    from .terminal import main
    main(sys.argv[2:])
elif len(sys.argv) == 1 or sys.argv[1] == "tui":
    from .tui import main
    main(sys.argv[2:] if len(sys.argv) > 1 else [])
else:
    from .cli import main
    main()
