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
        writer.writerow({'organisationID':'1','name':'Acme Payments','activityType':'PRC','SME':'true','country':'Poland','city':'Warsaw','organizationURL':'https://acme-payments.example'})
        writer.writerow({'organisationID':'2','name':'Example University','activityType':'HIE','SME':'false','country':'Germany','city':'Berlin','organizationURL':'https://university.example'})
        writer.writerow({'organisationID':'3','name':'Private AI GmbH','activityType':'Private for-profit','SME':'false','country':'Germany','city':'Munich','organizationURL':'www.private-ai.example'})
        writer.writerow({'organisationID':'4','name':'US Partner Inc','activityType':'PRC','SME':'true','country':'United States','city':'Boston','organizationURL':'https://uspartner.example'})
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('organization.csv', buf.getvalue())
        items = extract_cordis_companies(path)
        names = {x['name'] for x in items}
        assert names == {'Acme Payments','Private AI GmbH'}, items
        assert all(x['website'].startswith('http') for x in items)
        assert all('CORDIS' in x['tags'] for x in items)
    print('CORDIS parser test OK')


if __name__ == '__main__':
    main()
