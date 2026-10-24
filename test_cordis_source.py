from pathlib import Path
import csv
import io
import tempfile
import zipfile

from src.cordis_source import extract_cordis_companies


def main():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'cordis.zip'
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=['organisationID','name','activityType','SME','country','city','organizationURL'])
        writer.writeheader()
        writer.writerow({'organisationID':'1','name':'Acme Payments','activityType':'PRC','SME':'true','country':'PL','city':'Warsaw','organizationURL':'https://acme-payments.example'})
        writer.writerow({'organisationID':'2','name':'Example University','activityType':'HES','SME':'false','country':'DE','city':'Berlin','organizationURL':'https://university.example'})
        writer.writerow({'organisationID':'3','name':'Private AI GmbH','activityType':'PRC','SME':'false','country':'DE','city':'Munich','organizationURL':'www.private-ai.example'})
        writer.writerow({'organisationID':'4','name':'US Partner Inc','activityType':'PRC','SME':'true','country':'US','city':'Boston','organizationURL':'https://uspartner.example'})
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('organization.csv', buf.getvalue())

        horizon = extract_cordis_companies(path)
        names = {x['name'] for x in horizon}
        assert names == {'Acme Payments','Private AI GmbH'}, horizon
        by_name = {x['name']: x for x in horizon}
        assert by_name['Acme Payments']['extra']['country'] == 'Poland'
        assert by_name['Private AI GmbH']['extra']['country'] == 'Germany'
        assert all(x['website'].startswith('http') for x in horizon)
        assert all('CORDIS' in x['tags'] and 'Horizon Europe' in x['tags'] for x in horizon)

        h2020 = extract_cordis_companies(
            path,
            programme_label='Horizon 2020',
            dataset_url='https://cordis.europa.eu/data/cordis-h2020projects-csv.zip',
        )
        assert {x['name'] for x in h2020} == names
        assert all('Horizon 2020' in x['tags'] for x in h2020)
        assert all(x['extra']['cordis_programme'] == 'Horizon 2020' for x in h2020)
        assert all('Horizon 2020' in x['description'] for x in h2020)

    print('CORDIS Horizon Europe / H2020 parser test OK')


if __name__ == '__main__':
    main()
