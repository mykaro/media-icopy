"""Entry point for the GUI application."""

import sys
import logging

from .app import App


def main():
    # Set up basic error logging for the GUI itself
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    try:
        import pyi_splash

        # Close the splash screen after all heavy imports are done
        # and right before initializing the App window.
        if pyi_splash.is_alive():
            pyi_splash.close()
    except ImportError:
        pass

    try:
        app = App()
        app.mainloop()
    except Exception as e:
        logging.getLogger(__name__).error(f"GUI Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
