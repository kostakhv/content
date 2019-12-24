import demistomock as demisto
from CommonServerPython import *
from CommonServerUserPython import *

''' IMPORTS '''
import urllib3
import csv

# disable insecure warnings
urllib3.disable_warnings()

SOURCE_NAME = demisto.params().get('source_name')


class Client(BaseClient):
    def __init__(self, url: str, fieldnames: str, insecure: bool = False, credentials: dict = None,
                 ignore_regex: str = None, delimiter: str = ',', doublequote: bool = True, escapechar: str = '',
                 quotechar: str = '"', skipinitialspace: bool = False, polling_timeout: int = 20, proxy: bool = False,
                 **kwargs):
        """
        :param url: URL of the feed.
        :param fieldnames: list of field names in the file. If *null* the values in the first row of the file are
            used as names. Default: *null*
        :param insecure: boolean, if *false* feed HTTPS server certificate is verified. Default: *false*
        :param credentials: username and password used for basic authentication
        :param ignore_regex: python regular expression for lines that should be ignored. Default: *null*
        :param delimiter: see `csv Python module
            <https://docs.python.org/2/library/csv.html#dialects-and-formatting-parameters>`. Default: ,
        :param doublequote: see `csv Python module
            <https://docs.python.org/2/library/csv.html#dialects-and-formatting-parameters>`. Default: true
        :param escapechar: see `csv Python module
            <https://docs.python.org/2/library/csv.html#dialects-and-formatting-parameters>`. Default null
        :param quotechar: see `csv Python module
            <https://docs.python.org/2/library/csv.html#dialects-and-formatting-parameters>`. Default "
        :param skipinitialspace: see `csv Python module
            <https://docs.python.org/2/library/csv.html#dialects-and-formatting-parameters>`. Default False
        :param polling_timeout: timeout of the polling request in seconds. Default: 20
        :param proxy: Sets whether use proxy when sending requests
        :param kwargs:
        """
        if not credentials:
            credentials = {}
        username = credentials.get('identifier', None)
        password = credentials.get('password', None)
        auth = None
        if username is not None and password is not None:
            auth = (username, password)

        super().__init__(base_url=url, proxy=proxy, verify=not insecure, auth=auth)

        try:
            self.polling_timeout = int(polling_timeout)
        except (ValueError, TypeError):
            return_error('Please provide an integer value for "Request Timeout"')

        self.ignore_regex = ignore_regex
        if self.ignore_regex is not None:
            self.ignore_regex = re.compile(self.ignore_regex)  # type: ignore
        self.fieldnames = argToList(fieldnames)

        self.dialect = {
            'delimiter': delimiter,
            'doublequote': doublequote,
            'escapechar': escapechar,
            'quotechar': quotechar,
            'skipinitialspace': skipinitialspace
        }

    def _build_request(self):
        r = requests.Request(
            'GET',
            self._base_url,
            auth=self._auth
        )

        return r.prepare()

    def build_iterator(self):
        _session = requests.Session()

        prepreq = self._build_request()

        # this is to honour the proxy environment variables
        rkwargs = _session.merge_environment_settings(
            prepreq.url,
            {}, None, None, None  # defaults
        )
        rkwargs['stream'] = True
        rkwargs['verify'] = self._verify
        rkwargs['timeout'] = self.polling_timeout

        try:
            r = _session.send(prepreq, **rkwargs)
        except requests.ConnectionError:
            raise requests.ConnectionError('Failed to establish a new connection. Please make sure your URL is valid.')
        try:
            r.raise_for_status()
        except Exception:
            return_error('{} - exception in request: {} {}'.format(SOURCE_NAME, r.status_code, r.content))
            raise

        response = r.content.decode('latin-1').split('\n')
        if self.ignore_regex is not None:
            response = filter(
                lambda x: self.ignore_regex.match(x) is None,
                response
            )

        csvreader = csv.DictReader(
            response,
            fieldnames=self.fieldnames,
            **self.dialect
        )

        return csvreader


# simple function to iterate list in batches
def batch(iterable, batch_size=1):
    current_batch = []
    for item in iterable:
        current_batch.append(item)
        if len(current_batch) == batch_size:
            yield current_batch
            current_batch = []
    if current_batch:
        yield current_batch


def module_test_command(client, args):
    fieldnames = demisto.params().get('fieldnames')
    if fieldnames == 'indicator' or any(field in fieldnames for field in ('indicator,', ',indicator')):
        client.build_iterator()
        return 'ok', {}, {}
    return_error('Please provide a column named "indicator" in fieldnames')


def fetch_indicators_command(client, itype):
    # write _process_itemdoublequote here
    iterator = client.build_iterator()
    indicators = []
    for item in iterator:
        raw_json = dict(item)
        raw_json['value'] = value = item.get('indicator')
        raw_json['type'] = itype
        indicators.append({
            "value": value,
            "type": itype,
            "rawJSON": raw_json,
        })
    return indicators


def get_indicators_command(client, args):
    itype = args.get('indicator_type', demisto.params().get('indicator_type'))
    limit = int(args.get('limit'))
    indicators_list = fetch_indicators_command(client, itype)
    entry_result = camelize(indicators_list[:limit])
    hr = tableToMarkdown('Indicators', entry_result, headers=['Value', 'Type', 'Rawjson'])
    return hr, {'CSV.Indicator': entry_result}, indicators_list


def main():
    # Write configure here
    params = {k: v for k, v in demisto.params().items() if v is not None}
    handle_proxy()
    client = Client(**params)
    command = demisto.command()
    demisto.info('Command being called is {}'.format(command))
    # Switch case
    commands = {
        'test-module': module_test_command,
        'get-indicators': get_indicators_command
    }
    try:
        if demisto.command() == 'fetch-indicators':
            indicators = fetch_indicators_command(client, params.get('indicator_type'))
            # we submit the indicators in batches
            for b in batch(indicators, batch_size=2000):
                demisto.createIndicators(b)  # type: ignore
        else:
            readable_output, outputs, raw_response = commands[command](client, demisto.args())
            return_outputs(readable_output, outputs, raw_response)
    except Exception as e:
        err_msg = f'Error in {SOURCE_NAME} Integration [{e}]'
        return_error(err_msg)


if __name__ == '__builtin__' or __name__ == 'builtins':
    main()
