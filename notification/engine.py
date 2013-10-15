from __future__ import absolute_import, unicode_literals
import sys
import time
import logging
import traceback
from datetime import datetime
from multiprocessing import Pool
from multiprocessing.pool import ThreadPool
# from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

try:
    import cPickle as pickle
except ImportError:
    import pickle

from django.conf import settings
from django.core.mail import mail_admins
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.db import connections

from .lockfile import FileLock, AlreadyLocked, LockTimeout

from notification.models import NoticeQueueBatch
from notification import models as notification

# lock timeout value. how long to wait for the lock to become available.
# default behavior is to never wait for the lock to be available.
LOCK_WAIT_TIMEOUT = getattr(settings, "NOTIFICATION_LOCK_WAIT_TIMEOUT", -1)
NOTICEUID_MAX_SIZE = getattr(settings, "NOTIFICATION_NOTICEUID_MAX_SIZE", 100000)

logger = logging.getLogger(__name__)


def send_all(workers=1, processes=False):
    lock = FileLock("send_notices")

    logger.debug("acquiring lock...")
    try:
        lock.acquire(LOCK_WAIT_TIMEOUT)
    except AlreadyLocked:
        logger.debug("lock already in place. quitting.")
        return
    except LockTimeout:
        logger.debug("waiting for the lock timed out. quitting.")
        return
    logger.debug("acquired.")

    batches, sent = 0, {}
    logger.debug("started at %s", datetime.now())
    start_time = time.time()

    if workers > 1:
        if processes:
            logger.debug("Starting {0} Process workers.".format(workers))
            for conn_alias in connections:
                connections[conn_alias].close()
            pool = Pool(processes=workers)

        else:
            logger.debug("Starting {0} Thread workers.".format(workers))
            pool = ThreadPool(processes=workers)

    try:
        # nesting the try statement to be Python 2.4
        try:
            for queued_batch in NoticeQueueBatch.objects.order_by("pk"):
                notices = pickle.loads(str(queued_batch.pickled_data).decode("base64"))
                for users, label, extra_context, on_site, sender in notices:

                    if workers == 1:
                        result = _send_batch_part(users, label, extra_context, on_site, sender)
                        for k, v in result.items():
                            sent.setdefault(k, 0)
                            sent[k] += v
                    else:
                        results = pool.map(
                            _send_batch_part_mp,
                            ([part, label, extra_context, on_site, sender] for part in chunks(users, workers))
                         )
                        for result in results:
                            for k, v in result.items():
                                sent.setdefault(k, 0)
                                sent[k] += v

                queued_batch.delete()
                batches += 1

            uid_qs = notification.NoticeUid.objects.all()
            uid_size = uid_qs.count()
            if uid_size > NOTICEUID_MAX_SIZE:
                logger.debug("NoticeUid size is {0}, clearing...".format(uid_size))
                uid_step = min(int(NOTICEUID_MAX_SIZE * 0.1), 1000)
                uid_min = uid_qs.order_by("pk")[uid_step].pk
                uid_qs.filter(pk__lt=uid_min).delete()

        except:
            # get the exception
            exc_class, e, t = sys.exc_info()
            # email people
            current_site = Site.objects.get_current()
            subject = "[{0} emit_notices] {1!r}".format(current_site.name, e)
            message = "{0}".format("\n".join(traceback.format_exception(*sys.exc_info())),)
            mail_admins(subject, message, fail_silently=True)
            # log it as critical
            logger.critical("an exception occurred: {0!r}".format(e))

    finally:
        logger.debug("releasing lock...")
        lock.release()
        logger.debug("released.")

    logger.info("")
    logger.info("{0} batches, {1} sent".format(batches, sent))
    logger.info("done in {0:.2f} seconds".format(time.time() - start_time))
    logger.debug("done at %s", datetime.now())


def _send_batch_part(users, label, extra_context, on_site, sender):
    """Sends part of queued batch"""
    sent = {}
    for user in users:
        # The instance of QuerySet also can be pickled,
        # so, ckecks the instance of user.
        if not isinstance(user, User):
            try:
                logger.info("loading user {0}".format(user))
                user = User.objects.get(pk=user)
            except User.DoesNotExist:
                # Ignore deleted users, just warn about them
                logger.warning("not emitting notice {0} to user {1} since it does not exist".format(label, user))
                continue

        logger.info("emitting notice {0} to {1}".format(label, user))
        # call this once per user to be atomic and allow for logger to
        # accurately show how long each takes.
        try:
            result = notification.send_now([user], label, extra_context, on_site, sender)
        except ObjectDoesNotExist as e:
            logger.warning("Can't to emit notice {0} to user {1} since {2}".format(label, user, e))
        else:
            for k, v in result.items():
                sent.setdefault(k, 0)
                sent[k] += v

    return sent


def _send_batch_part_mp(args):
    """Sends part of queued batch in multiprocessing"""
    return _send_batch_part(*args)


def chunks(l, n):
    """ Yield successive n-sized chunks from l."""
    for i in xrange(0, len(l), n):
        yield l[i:i+n]
