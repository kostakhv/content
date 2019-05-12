import demistomock as demisto
from CommonServerPython import *
from CommonServerUserPython import *
''' IMPORTS '''

import json
import requests
from typing import Callable

# Disable insecure warnings
requests.packages.urllib3.disable_warnings()

''' TYPES '''

Response = requests.models.Response


''' GLOBALS/PARAMS '''

USERNAME: str = demisto.params().get('credentials').get('identifier')
PASSWORD: str = demisto.params().get('credentials').get('password')
SERVER: str = (demisto.params()['url'][:-1]
               if (demisto.params()['url'] and demisto.params()['url'].endswith('/')) else demisto.params()['url'])
USE_SSL: bool = not demisto.params().get('insecure', False)
BASE_URL: str = SERVER + '/api/v1/'
HEADERS: dict = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
}
NONE_DATE: str = '0001-01-01T00:00:00Z'

FETCH_TIME: str = demisto.params().get('fetch_time', '').strip()
FETCH_LIMIT: str = demisto.params().get('fetch_limit', '10')
RAISE_EXCEPTION_ON_ERROR: bool = False


''' HELPER FUNCTIONS '''


def http_request(method: str, path: str, params: dict = None, data: dict = None) -> dict:
    """
    Sends an HTTP request using the provided arguments
    :param method: HTTP method
    :param path: URL path
    :param params: URL query params
    :param data: Request body
    :return: JSON response
    """
    params: dict = params if params is not None else {}
    data: dict = data if data is not None else {}

    try:
        res: Response = requests.request(
            method,
            BASE_URL + path,
            auth=(USERNAME, PASSWORD),
            verify=USE_SSL,
            params=params,
            data=json.dumps(data),
            headers=HEADERS)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
            requests.exceptions.TooManyRedirects, requests.exceptions.RequestException) as e:
        return return_error('Could not connect to PhishLabs IOC Feed: {}'.format(str(e)))

    if res.status_code < 200 or res.status_code > 300:
        status: int = res.status_code
        message: str = res.reason
        details: str = ''
        try:
            error_json: dict = res.json()
            message = error_json.get('statusMessage', '')
            details = error_json.get('message', '')
        except Exception:
            pass
        error_message: str = ('Error in API call to PhishLabs IOC API, status code: {}, reason: {}, details: {}'
                              .format(status, message, details))
        if RAISE_EXCEPTION_ON_ERROR:
            raise Exception(error_message)
        else:
            return return_error(error_message)
    try:
        return res.json()
    except Exception:
        error_message = 'Failed parsing the response from PhishLabs IOC API: {}'.format(res.content)
        if RAISE_EXCEPTION_ON_ERROR:
            raise Exception(error_message)
        else:
            return return_error(error_message)


def populate_context(dbot_scores: list, domain_entries: list, file_entries: list,
                     url_entries: list, email_entries: list = None) -> dict:
    """
    Populate the context object with entries as tuples -
    the first element contains global objects and the second contains PhishLabs objects
    :param dbot_scores: Indicator DBotScore
    :param domain_entries: Domain indicators
    :param file_entries: File indicators
    :param url_entries: URL indicators
    :param email_entries: Email indicators
    :return: The context object
    """
    context: dict = {}
    if url_entries:
        context[outputPaths['url']] = createContext(list(map(lambda u: u[0], url_entries)))
        context['PhishLabs.URL(val.ID && val.ID === obj.ID)'] = createContext(list(map(lambda u: u[1], url_entries)))
    if domain_entries:
        context[outputPaths['domain']] = createContext(list(map(lambda d: d[0], domain_entries)))
        context['PhishLabs.Domain(val.ID && val.ID === obj.ID)'] = createContext(list(map(lambda d: d[1],
                                                                                          domain_entries)))
    if file_entries:
        context[outputPaths['file']] = createContext(list(map(lambda f: f[0], file_entries)))
        context['PhishLabs.File(val.ID && val.ID === obj.ID)'] = createContext(list(map(lambda f: f[1], file_entries)))
    if email_entries:
        context['Email'] = createContext(list(map(lambda e: e[0], email_entries)))
        context['PhishLabs.Email(val.ID && val.ID === obj.ID)'] = createContext(list(map(lambda e: e[1],
                                                                                         email_entries)))
    if dbot_scores:
        context[outputPaths['dbotscore']] = dbot_scores
    return context


def get_file_properties(indicator: dict) -> tuple:
    """
    Extract the file properties from the indicator attributes
    :param indicator: The file indicator
    :return: File MD5, name and type
    """
    file_name_attribute: list = list(filter(lambda a: a.get('name') == 'name', indicator.get('attributes', [])))
    file_name: str = file_name_attribute[0].get('value') if file_name_attribute else ''
    file_type_attribute: list = list(filter(lambda a: a.get('name') == 'filetype', indicator.get('attributes', [])))
    file_type: str = file_type_attribute[0].get('value') if file_type_attribute else ''
    file_md5_attribute: list = list(filter(lambda a: a.get('name') == 'md5', indicator.get('attributes', [])))
    file_md5: str = file_md5_attribute[0].get('value') if file_md5_attribute else ''

    return file_md5, file_name, file_type


def get_email_properties(indicator: dict) -> tuple:
    """
    Extract the email properties from the indicator attributes
    :param indicator: The email indicator
    :return: Email body, To and From
    """
    email_to_attribute: list = list(filter(lambda a: a.get('name') == 'to', indicator.get('attributes', [])))
    email_to: str = email_to_attribute[0].get('value') if email_to_attribute else ''
    email_from_attribute: list = list(filter(lambda a: a.get('name') == 'from', indicator.get('attributes', [])))
    email_from: str = email_from_attribute[0].get('value') if email_from_attribute else ''
    email_body_attribute: list = list(filter(lambda a: a.get('name') == 'email-body', indicator.get('attributes', [])))
    email_body: str = email_body_attribute[0].get('value') if email_body_attribute else ''

    return email_body, email_to, email_from


def create_domain_context(indicator: dict) -> dict:
    """
    Create a domain context object
    :param indicator: The domain indicator
    :return: The domain context object
    """
    return {
        'Name': indicator.get('value')
    }


def create_url_context(indicator: dict, classification: str) -> dict:
    """
    Create a URL context object
    :param indicator: The URL indicator
    :param classification: The indicator classification
    :return: The URL context object
    """

    url_object: dict = {
        'Data': indicator.get('value')
    }

    if classification == 'Malicious':
        url_object['Malicious'] = {
            'Vendor': 'PhishLabs',
            'Description': 'URL in PhishLabs feed'
        }

    return url_object


def create_phishlabs_object(indicator: dict) -> dict:
    """
    Create the context object for the PhishLabs path
    :param indicator: The indicator
    :return: The context object
    """
    return {
        'ID': indicator.get('id'),
        'CreatedAt': indicator.get('createdAt'),
        'UpdatedAt': indicator.get('updatedAt'),
        'Type': indicator.get('type'),
        'Attribute': [{
            'Name': a.get('name'),
            'Type': a.get('type'),
            'Value': a.get('value'),
            'CreatedAt': a.get('createdAt')
        } for a in indicator.get('attributes', [])]
    }


def create_indicator_content(indicator: dict) -> dict:
    """
    Create content for the human readable object
    :param indicator: The indicator
    :return: The object to return to the War Room
    """
    return {
        'ID': indicator.get('id'),
        'Indicator': indicator.get('value'),
        'Type': indicator.get('type'),
        'CreatedAt': indicator.get('createdAt'),
        'UpdatedAt': indicator['updatedAt'] if indicator.get('updatedAt', '') != NONE_DATE else '',
        'FalsePositive': indicator.get('falsePositive')
    }


''' COMMANDS'''


def test_module():
    """
    Performs basic get request to get item samples
    """
    get_global_feed_request(limit='1')
    demisto.results('ok')


def get_global_feed_command():
    """
    Gets the global feed data using the provided arguments
    """
    indicator_headers: list = ['Indicator', 'Type', 'CreatedAt', 'UpdatedAt', 'ID', 'FalsePositive']
    contents: list = []
    url_entries: list = []
    domain_entries: list = []
    file_entries: list = []
    dbot_scores: list = []
    context: dict = {}

    since: str = demisto.args().get('since')
    limit: str = demisto.args().get('limit')
    indicator: list = argToList(demisto.args().get('indicator_type', []))
    offset: str = demisto.args().get('offset')
    remove_protocol: str = demisto.args().get('remove_protocol')
    remove_query: str = demisto.args().get('remove_query')
    false_positive: str = demisto.args().get('false_positive')

    feed: dict = get_global_feed_request(since, limit, indicator, offset, remove_protocol, remove_query, false_positive)

    if feed and feed.get('data'):
        results: list = feed['data']

        for result in results:
            contents.append(create_indicator_content(result))

            indicator_type: str = result.get('type')
            phishlabs_object: dict = create_phishlabs_object(result)

            dbot_score: dict = {
                'Indicator': result.get('value'),
                'Vendor': 'PhishLabs',
                'Score': 3
            }

            if indicator_type == 'URL':
                context_object = create_url_context(result, 'Malicious')
                phishlabs_object['Data'] = result.get('value')
                dbot_score['type'] = 'url'
                url_entries.append((context_object, phishlabs_object))

            elif indicator_type == 'Domain':
                context_object = create_domain_context(result)
                phishlabs_object['Name'] = result.get('value')
                dbot_score['type'] = 'domain'
                domain_entries.append((context_object, phishlabs_object))

            elif indicator_type == 'Attachment':
                file_md5, file_name, file_type = get_file_properties(result)

                context_object = {
                    'Name': file_name,
                    'Type': file_type,
                    'MD5': file_md5
                }

                phishlabs_object['Name'] = file_name
                phishlabs_object['Type'] = file_type
                phishlabs_object['MD5'] = file_md5

                file_entries.append((context_object, phishlabs_object))
                dbot_score['type'] = 'file'

            dbot_scores.append(dbot_score)

        context = populate_context(dbot_scores, domain_entries, file_entries, url_entries)
        human_readable: str = tableToMarkdown('PhishLabs Global Feed', contents, headers=indicator_headers,
                                              removeNull=True, headerTransform=pascalToSpace)
    else:
        human_readable = 'No indicators found'

    return_outputs(human_readable, context, feed)


def get_global_feed_request(since: str = None, limit: str = None, indicator: list = None, offset: str = None,
                            remove_protocol: str = None, remove_query: str = None, false_positive: str = None) -> dict:
    """
    Sends a request to PhishLabs global feed with the provided arguments
    :param since: Data updated within this duration of time from now
    :param limit: Limit the number of rows to return
    :param indicator: Indicator type filter
    :param offset: Number of rows to skip
    :param remove_protocol: Removes the protocol part from indicators when the rule can be applied.
    :param remove_query: Removes the query string part from indicators when the rules can be applied.
    :param false_positive: Filter by indicators that are false positives.
    :return: Global feed indicators
    """
    path: str = 'globalfeed'
    params: dict = {}

    if since:
        params['since'] = since
    if limit:
        params['limit'] = int(limit)
    if offset:
        params['offset'] = int(offset)
    if indicator:
        params['indicator'] = indicator
    if remove_protocol:
        params['remove_protocol'] = remove_protocol
    if remove_query:
        params['remove_query'] = remove_query
    if false_positive:
        params['false_positive'] = false_positive

    response = http_request('GET', path, params)

    return response


def get_incident_indicators_command():
    """
    Gets the indicators for the specified incident
    """
    indicator_headers: list = ['Indicator', 'Type', 'CreatedAt', 'UpdatedAt', 'ID', 'FalsePositive']
    attribute_headers: list = ['Name', 'Type', 'Value', 'CreatedAt']
    url_entries: list = []
    domain_entries: list = []
    file_entries: list = []
    email_entries: list = []
    dbot_scores: list = []
    context: dict = {}

    incident_id: str = demisto.args().get('id')
    since: str = demisto.args().get('since')
    limit: str = demisto.args().get('limit')
    indicator: list = argToList(demisto.args().get('indicator_type', []))
    offset: str = demisto.args().get('offset')
    classification: str = demisto.args().get('indicators_classification', 'Suspicious')
    human_readable: str = 'Indicators for incident ' + incident_id + '\n'

    feed: dict = get_feed_request(since, limit, indicator, offset)
    if feed and feed.get('data'):
        results: list = list(filter(lambda f: f.get('referenceId', '') == incident_id, feed['data']))
        if results:
            for result in results[0].get('indicators', []):
                human_readable += tableToMarkdown('Indicator', create_indicator_content(result),
                                                  headers=indicator_headers,
                                                  removeNull=True, headerTransform=pascalToSpace)
                phishlabs_object = create_phishlabs_object(result)

                if phishlabs_object.get('Attribute'):
                    human_readable += tableToMarkdown('Attributes', phishlabs_object['Attribute'],
                                                      headers=attribute_headers,
                                                      removeNull=True, headerTransform=pascalToSpace)
                else:
                    human_readable += 'No attributes for this indicator'

                indicator_type: str = result.get('type')

                dbot_score: dict = {
                    'Indicator': result.get('value'),
                    'Vendor': 'PhishLabs',
                    'Score': 3 if classification == 'Malicious' else 2
                }

                if indicator_type == 'URL':
                    context_object = create_url_context(result, classification)
                    phishlabs_object['Data'] = result.get('value')
                    dbot_score['type'] = 'url'
                    url_entries.append((context_object, phishlabs_object))

                elif indicator_type == 'Domain':
                    context_object = create_domain_context(result)
                    phishlabs_object['Name'] = result.get('value')
                    dbot_score['type'] = 'domain'
                    domain_entries.append((context_object, phishlabs_object))

                elif indicator_type == 'Attachment':
                    file_md5, file_name, file_type = get_file_properties(result)

                    context_object = {
                        'Name': file_name,
                        'Type': file_type,
                        'MD5': file_md5
                    }

                    phishlabs_object['Name'] = file_name
                    phishlabs_object['Type'] = file_type
                    phishlabs_object['MD5'] = file_md5

                    file_entries.append((context_object, phishlabs_object))
                    dbot_score['type'] = 'file'

                elif indicator_type == 'E-mail':
                    email_body, email_to, email_from = get_email_properties(result)

                    context_object = {
                        'To': email_to,
                        'From': email_from,
                        'Body': email_body,
                        'Subject': result.get('value')
                    }

                    phishlabs_object['To'] = email_to,
                    phishlabs_object['From'] = email_from,
                    phishlabs_object['Body'] = email_body
                    phishlabs_object['Subject'] = result.get('value')

                    email_entries.append((context_object, phishlabs_object))

                if indicator_type != 'E-mail':
                    # We do not know what we have for an email
                    dbot_scores.append(dbot_score)

            context = populate_context(dbot_scores, domain_entries, file_entries, url_entries, email_entries)
        else:
            human_readable = 'Incident not found, check your arguments'
    else:
        human_readable = 'No incidents found, check your arguments'

    return_outputs(human_readable, context, feed)


def get_feed_request(since: str = None, limit: str = None, indicator: list = None, offset: str = None) -> dict:
    """
    Sends a request to PhishLabs user feed with the provided arguments
    :param since: Data updated within this duration of time from now
    :param limit: Limit the number of rows to return
    :param indicator: Indicator type filter
    :param offset: Number of rows to skip
    :return: User feed
    """
    path: str = 'feed'
    params: dict = {}

    if since:
        params['since'] = since
    if limit:
        params['limit'] = int(limit)
    if offset:
        params['offset'] = int(offset)
    if indicator:
        params['indicator'] = indicator

    response = http_request('GET', path, params)

    return response


def fetch_incidents():
    """
    Fetches incidents from the PhishLabs user feed.
    :return: Demisto incidents
    """
    last_run: dict = demisto.getLastRun()
    last_fetch: str = last_run.get('time', '') if last_run else ''

    incidents: list = []
    count: int = 0
    feed: dict = get_feed_request(since=FETCH_TIME, limit=FETCH_LIMIT)
    last_fetch_time: datetime = (datetime.strptime(last_fetch, '%Y-%m-%dT%H:%M:%SZ') if last_fetch
                                 else datetime.strptime(NONE_DATE, '%Y-%m-%dT%H:%M:%SZ'))
    max_time: datetime = last_fetch_time
    results: list = feed.get('data', [])
    for result in results:
        if count > int(FETCH_LIMIT):
            break
        incident_time: datetime = datetime.strptime(result.get('createdAt', NONE_DATE), '%Y-%m-%dT%H:%M:%SZ')
        if last_fetch_time and incident_time <= last_fetch_time:
            continue

        incident: dict = {
            'name': 'PhishLabs IOC Incident ' + result.get('referenceId'),
            # 'occurred': datetime.strftime(incident_time, '%Y-%m-%dT%H:%M:%S'),
            'rawJSON': json.dumps(result)
        }
        incidents.append(incident)
        if max_time < incident_time:
            max_time = incident_time
        count += 1

    demisto.incidents(incidents)
    demisto.setLastRun({'time': datetime.strftime(max_time, '%Y-%m-%dT%H:%M:%SZ')})


''' COMMANDS MANAGER / SWITCH PANEL '''

LOG('Command being called is {}'.format(demisto.command()))
handle_proxy()

COMMAND_DICT = {
    'test-module': test_module,
    'fetch-incidents': fetch_incidents,
    'phishlabs-global-feed': get_global_feed_command,
    'phishlabs-get-incident-indicators': get_incident_indicators_command
}

try:
    command_func: Callable = COMMAND_DICT[demisto.command()]
    if demisto.command() == 'fetch-incidents':
        RAISE_EXCEPTION_ON_ERROR = True
    command_func()

except Exception as e:
    LOG(str(e))
    LOG.print_log()
    if RAISE_EXCEPTION_ON_ERROR:
        raise
    else:
        return_error(str(e))
