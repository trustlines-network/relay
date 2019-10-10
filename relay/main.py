# Make external libs work with gevent, but still enable real threading
from gevent import monkey

monkey.patch_all(thread=False)  # noqa: E702
# Make postgresql usable with gevent
import psycogreen.gevent

psycogreen.gevent.patch_psycopg()  # noqa: E702
import logging

import click
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler
from relay.utils import get_version

from relay.relay import TrustlinesRelay
from .api.app import ApiApp
import json

logger = logging.getLogger("trustlines")


def patch_warnings_module():
    """patch the warnings modules simplefilter function

    the web3 module prints excessive deprecation warnings. They call

      warnings.simplefilter('always', DeprecationWarning)

    in web3.utils.decorators before calling into warnings.warn. So, we need to
    take some drastic measures to prevent the flood of deprecation warnings
    cluttering all of our logs.

    We replace warnings.simplefilter with a function that does nothing when
    called with category=DeprecationWarning.
    """
    import warnings

    orig_simplefilter = warnings.simplefilter

    def simplefilter(action, category=Warning, lineno=0, append=False):
        if category is DeprecationWarning:
            return
        return orig_simplefilter(
            action, category=category, lineno=lineno, append=append
        )

    warnings.simplefilter = simplefilter
    logger.info(
        "the warnings module has been patched. You will not see the DeprecationWarning messages from web3"
    )


def _show_version(ctx, param, value):
    """handle --version argumemt

    we need this function, because otherwise click may check that the default
    --config or --addresses arguments are really files and they may not
    exist"""
    if value:
        click.echo(get_version())
        ctx.exit()


def load_config(config_file_path):
    with open(config_file_path) as data_file:
        return json.load(data_file)


def configure_logging(config):
    """configure the logging subsystem via the 'logging' key in the json config"""
    logging.basicConfig(format="%(asctime)s[%(levelname)s] %(name)s: %(message)s")
    try:
        logging.config.dictConfig(config["logging"])
    except (ValueError, TypeError, AttributeError, ImportError) as err:
        click.echo(
            f"Error configuring logging: {err}\n"
            "Please check your configuration file and the LOGLEVEL environment variable"
        )
        raise click.Abort()

    logger.debug(
        "Initialized logging system with the following config: %r", config["logging"]
    )


@click.command()
@click.option("--port", default=5000, show_default=True, help="port to listen on")
@click.option(
    "--config",
    "config_path",
    default="config.json",
    help="path to json configuration file",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--addresses",
    default="addresses.json",
    help="path to addresses json file",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--version",
    help="Prints the version of the software",
    is_flag=True,
    callback=_show_version,
)
@click.pass_context
def main(ctx, port, config_path, addresses, version):
    """run the relay server"""
    config = load_config(config_path)
    configure_logging(config)
    logger.info("Starting relay server version %s", get_version())
    # silence warnings from urllib3, see github issue 246
    urllib3_logger = logging.getLogger("urllib3.connectionpool")
    urllib3_logger.level = logging.CRITICAL

    # TODO: My plan is to no longer give the path to TrustlinesRelay but to give it the config dict
    trustlines = TrustlinesRelay(
        config_json_path=config_path, addresses_json_path=addresses
    )
    trustlines.start()
    ipport = ("", port)
    app = ApiApp(trustlines)
    http_server = WSGIServer(ipport, app, log=None, handler_class=WebSocketHandler)
    logger.info("Server is running on {}".format(ipport))
    http_server.serve_forever()


if __name__ == "__main__":
    main()
