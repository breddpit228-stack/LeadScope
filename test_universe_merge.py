from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import src.universe_merge as merge


def make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute('''CREATE TABLE companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT NOT NULL,
            website TEXT DEFAULT '',
            country TEXT DEFAULT '',
            city TEXT DEFAULT '',
            segment TEXT DEFAULT '',
            team_size_public TEXT DEFAULT '',
            public_signals TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            seed_source TEXT DEFAULT '',
            seed_tags_json TEXT DEFAULT '[]',
            quality_status TEXT DEFAULT '',
            data_origin TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )''')
        conn.execute('''INSERT INTO companies
            (company,website,country,city,segment,team_size_public,public_signals,source_url,seed_source,seed_tags_json,quality_status,data_origin,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            'Existing PayCo','https://payco.example','','','Technology','','','',
            'Public startup data','[]','','public_seed','2026-01-01','2026-01-01'
        ))
        conn.execute('''INSERT INTO companies
            (company,website,country,city,segment,team_size_public,public_signals,source_url,seed_source,seed_tags_json,quality_status,data_origin,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
            'Researched Co','https://researched.example','Germany','','Fintech','120',
            'Strong verified description from prior research.','https://researched.example',
            'Manual','["Fintech"]','Ready for review','manual','2026-01-01','2026-01-01'
        ))
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'universe.db'
        make_db(path)
        original = merge.DB_PATH
        merge.DB_PATH = path
        try:
            result = merge.merge_company_items([
                {
                    'name':'Existing PayCo',
                    'website':'https://www.payco.example/about',
                    'description':'Payment processing and accounting software for European businesses.',
                    'tags':['payment processing'],
                    'source_url':'https://www.wikidata.org/wiki/Q1',
                    'extra':{'country':'Poland','team_size_public':'75'},
                },
                {
                    'name':'New AI Co',
                    'website':'https://newai.example',
                    'description':'Machine learning and data analytics platform for enterprise teams.',
                    'tags':['machine learning'],
                    'source_url':'https://www.wikidata.org/wiki/Q2',
                    'extra':{'country':'France','team_size_public':'42'},
                },
                {
                    'name':'Researched Co',
                    'website':'https://researched.example',
                    'description':'Germany company indexed from Wikidata with an official website.',
                    'tags':['Wikidata'],
                    'source_url':'https://www.wikidata.org/wiki/Q3',
                    'extra':{'country':'Germany'},
                },
            ], limit=10, source_name='Wikidata · test')
            assert result['added'] == 1, result
            assert result['updated'] >= 2, result

            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            try:
                payco = dict(conn.execute("SELECT * FROM companies WHERE website='https://payco.example'").fetchone())
                assert payco['country'] == 'Poland', payco
                assert payco['team_size_public'] == '75', payco
                assert payco['segment'] == 'Fintech', payco
                assert 'payment' in payco['public_signals'].lower(), payco
                assert 'Wikidata' in payco['seed_source'], payco

                newco = dict(conn.execute("SELECT * FROM companies WHERE website='https://newai.example'").fetchone())
                assert newco['segment'] == 'AI & Data', newco
                assert newco['country'] == 'France', newco

                researched = dict(conn.execute("SELECT * FROM companies WHERE website='https://researched.example'").fetchone())
                assert researched['public_signals'] == 'Strong verified description from prior research.', researched

                audit = merge.duplicate_domain_audit()
                assert audit['duplicate_domains'] == 0, audit
            finally:
                conn.close()
        finally:
            merge.DB_PATH = original

    print('Company Universe merge test OK')


if __name__ == '__main__':
    main()
