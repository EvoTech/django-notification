
VALID_FILTERS = ('exact', 'startswith', 'endswith', 'contains', )


def get_field_values(instance):
    """Returns dict of instance's values."""
    return dict([(key, value) for key, value in instance.__dict__.iteritems() if not key.startswith('_')])


# TODO: suppports for FK, M2M, O2O, O2M, "OR" conditions, parentheses, "in" multiple values
class MatchFilter(object):
    def __init__(self, filters_string=None, fields=None, model=None):
        self.model = model
        self.fields = []

        if fields:
            self.fields = fields
        elif model:
            self.fields = [field.attname for field in model._meta.fields]
        self.filters = self._parse_filters(filters_string)

    def is_valid(self):
        """Returns True if a given match filter is valid, else - False."""
        return self.filters is not False

    def matches(self, obj_or_dict):
        """
        Returns True if obj_or_dict matches the given filters, else - False.
        """
        if isinstance(obj_or_dict, (dict, )):
            obj_dict = obj_or_dict
        else:
            obj_dict = get_field_values(obj_or_dict)
        for (field, (value, type)) in self.filters.iteritems():
            if type == 'contains':
                matches = obj_dict[field].find(value) != -1
            elif type == 'startswith':
                matches = obj_dict[field].startswith(value)
            elif type == 'endswith':
                matches = obj_dict[field].endswith(value)
            elif type == 'exact':
                matches = obj_dict[field] == value

            if not matches:
                return False

        return True

    def _parse_filters(self, filters_string):
        """
        Parses filters from a string and returns a dictionary of filters on
        success, False if the filters are not valid.
        """
        if filters_string is None:
            filters_string = ''
        parts = filters_string.split(',')
        filters = [filter.split('=') for filter in parts]

        filters_cleaned = {}
        for filter in filters:
            field = filter[0]

            if field in filters_cleaned.keys():
                # Filter for this field already exists, skip it.
                continue

            try:
                value = filter[1]
            except IndexError:
                # Missing filter value
                return False

            if field not in self.fields:
                # Object does not contain this field
                return False

            type, value = self._get_filter_type_and_value(value)

            if value.isdigit():
                value = int(value)
            elif value.lower() == 'true':
                value = True
            elif value.lower() == 'false':
                value = False
            elif value.lower() == 'none':
                value = None

            filters_cleaned[field] = (value, type)

        return filters_cleaned

    def _get_filter_type_and_value(self, value):
        """
        Returns a filter type and a value.
        """
        if value.startswith('*') and value.endswith('*'):
            return ('contains', value[1:-1], )
        elif value.startswith('*'):
            return ('endswith', value[1:], )
        elif value.endswith('*'):
            return ('startswith', value[:-1], )
        return ('exact', value, )
