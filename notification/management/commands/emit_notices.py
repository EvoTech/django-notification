import logging
from optparse import make_option
from django.core.management.base import BaseCommand
from notification.engine import send_all


class Command(BaseCommand):
    help = "Emit queued notices."

    option_list = BaseCommand.option_list + (
        make_option('-w', '--workers', dest='workers', type='int',
                    help='Number of workers used to emit notices', default=1),
        make_option('-p', '--processes', dest='processes', action='store_true',
                    help='Use process pool instead of thread pool', default=False),
    )

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
        logging.info("-" * 72)
        send_all(workers=options['workers'], processes=options['processes'])
