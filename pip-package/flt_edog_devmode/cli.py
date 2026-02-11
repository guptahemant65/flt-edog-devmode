"""CLI entry point for FLT EDOG DevMode."""

def main():
    """Main entry point for the edog command."""
    from .core import main as core_main
    core_main()

if __name__ == "__main__":
    main()
