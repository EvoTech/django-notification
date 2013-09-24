import logging
from optparse import make_option
from django.core.management.base import BaseCommand
from notification.engine import send_all


class Command(BaseCommand):
    help = "Emit queued notices."

    option_list = BaseCommand.option_list + (
        make_option('-w', '--workers', type='int',
                    help='Number of workers used to emit notices', default=1),
    )

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.DEBUG, format="%(message)s")
        logging.info("-" * 72)
        send_all(options['workers'])
