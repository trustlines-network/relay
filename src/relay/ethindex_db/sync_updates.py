import logging
import os.path
from typing import Dict, List, Union

import attr

logger = logging.getLogger("sync_updates")

SYNC_FILE_PATH = "last_graph_feed_sync_id"


@attr.s()
class TrustlineUpdateFeedUpdate:
    args: Dict = attr.ib()
    address: str = attr.ib()
    timestamp: int = attr.ib()

    @property
    def from_(self):
        return self.args.get("_creditor")

    @property
    def to(self):
        return self.args.get("_debtor")

    @property
    def creditline_given(self):
        return self.args.get("_creditlineGiven")

    @property
    def creditline_received(self):
        return self.args.get("_creditlineReceived")

    @property
    def interest_rate_given(self):
        return self.args.get("_interestRateGiven", 0)

    @property
    def interest_rate_received(self):
        return self.args.get("_interestRateReceived", 0)

    @property
    def is_frozen(self):
        return self.args.get("_isFrozen")


@attr.s()
class BalanceUpdateFeedUpdate:
    args: Dict = attr.ib()
    address: str = attr.ib()
    timestamp: int = attr.ib()

    @property
    def value(self):
        return self.args.get("_value")

    @property
    def from_(self):
        return self.args.get("_from")

    @property
    def to(self):
        return self.args.get("_to")


def graph_update_getter():
    ensure_graph_sync_id_file_exists()
    return get_graph_updates_feed


def get_graph_updates_feed(
    conn,
) -> List[Union[TrustlineUpdateFeedUpdate, BalanceUpdateFeedUpdate]]:
    """Get a list of updates to be applied on the trustlines graphs to make them up to date with the chain"""

    last_synced_graph_id = get_latest_graph_sync_id()

    query_string = """
        SELECT * FROM graphfeed WHERE id>%s ORDER BY id ASC;
    """

    with conn.cursor() as cur:
        cur.execute(query_string, [last_synced_graph_id])
        rows = cur.fetchall()

    feed_update: List[Union[TrustlineUpdateFeedUpdate, BalanceUpdateFeedUpdate]] = []

    for row in rows:
        event_type = row.get("eventname", None)
        if event_type == "TrustlineUpdate":
            feed_update.append(
                TrustlineUpdateFeedUpdate(
                    args=row["args"], address=row["address"], timestamp=row["timestamp"]
                )
            )
        elif event_type == "BalanceUpdate":
            feed_update.append(
                BalanceUpdateFeedUpdate(
                    args=row["args"], address=row["address"], timestamp=row["timestamp"]
                )
            )
        else:
            logger.warning(f"Got feed update with unknown type from database: {row}")

    if len(rows) >= 1:
        write_graph_sync_id_file(rows[len(rows) - 1]["id"])

    return feed_update


def write_graph_sync_id_file(sync_id: int):
    with open(SYNC_FILE_PATH, "w") as f:
        f.write(
            "#### This file contains the last synced graph feed id from the database ###\n"
            + str(sync_id)
        )


def ensure_graph_sync_id_file_exists():
    if not os.path.isfile(SYNC_FILE_PATH):
        write_graph_sync_id_file(0)


def get_latest_graph_sync_id():
    if not os.path.isfile(SYNC_FILE_PATH):
        raise ValueError("The last synced graph feed id file doesn't exist")

    with open(SYNC_FILE_PATH, "r") as f:
        contents = f.read()

    # first line is a comment
    # second line which we return is the last synced id
    return contents.split("\n")[1]
