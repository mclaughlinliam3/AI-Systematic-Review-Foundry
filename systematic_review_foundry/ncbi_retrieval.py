"""
NCBI PubMed source retrieval for the Systematic Review Foundry.
Adapted from the original sourcing.py with improvements.
"""
import requests
import xml.etree.ElementTree as ET
import unicodedata
from typing import List, Dict, Optional, Tuple
from time import sleep

from models import Source


def normalize_doi(doi: Optional[str]) -> Optional[str]:
    return doi.lower().strip() if doi else None


def search_pubmed(query: str, api_key: str, retmax: int = 100,
                  sort: str = 'relevance') -> List[Dict]:
    """Search PubMed and return parsed article metadata."""
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    sort_map = {
        'relevance': 'relevance',
        'pub_date': 'date',
        'first_author': 'author',
        'journal': 'journal'
    }
    if sort not in sort_map:
        sort = 'relevance'

    search_params = {
        "db": "pubmed", "term": query, "retmax": retmax,
        "usehistory": "y", "api_key": api_key, "sort": sort_map[sort]
    }

    try:
        response = requests.get(f"{base_url}esearch.fcgi", params=search_params, timeout=30)
        response.raise_for_status()
        search_tree = ET.fromstring(response.content)

        web_env_el = search_tree.find("WebEnv")
        query_key_el = search_tree.find("QueryKey")
        if web_env_el is None or query_key_el is None:
            return []

        fetch_params = {
            "db": "pubmed", "query_key": query_key_el.text,
            "WebEnv": web_env_el.text, "retmax": retmax,
            "retmode": "xml", "api_key": api_key
        }
        response = requests.get(f"{base_url}efetch.fcgi", params=fetch_params, timeout=60)
        response.raise_for_status()
        fetch_tree = ET.fromstring(response.content)
    except Exception as e:
        print(f"PubMed search error: {e}")
        return []

    results = []
    for article in fetch_tree.findall(".//PubmedArticle"):
        title_el = article.find(".//ArticleTitle")
        title = title_el.text if title_el is not None and title_el.text else "No title"

        abstract_el = article.find(".//Abstract/AbstractText")
        abstract_text = abstract_el.text if abstract_el is not None and abstract_el.text else None

        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text if pmid_el is not None else None

        pmc_el = article.find(".//ArticleId[@IdType='pmc']")
        pmc_id = pmc_el.text if pmc_el is not None else None

        doi_el = article.find(".//ArticleId[@IdType='doi']")
        doi = doi_el.text if doi_el is not None else None

        citation, journal, year = _construct_citation(article, doi)

        results.append({
            "title": title, "abstract": abstract_text,
            "pmid": pmid, "pmc_id": pmc_id,
            "citation": citation, "doi": normalize_doi(doi),
            "year": year, "journal": journal,
            "full_text": None
        })

    return results


def get_full_text(pmc_id: str, api_key: str) -> Optional[str]:
    """Retrieve full text from PMC."""
    if not pmc_id:
        return None
    if not pmc_id.startswith('PMC'):
        pmc_id = f'PMC{pmc_id}'

    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    params = {"db": "pmc", "id": pmc_id, "retmode": "xml", "api_key": api_key}

    try:
        response = requests.get(f"{base_url}efetch.fcgi", params=params, timeout=15)
        if response.status_code != 200:
            return None
        tree = ET.fromstring(response.content)

        parts = []
        for p in tree.findall(".//abstract//p"):
            text = _get_element_text(p)
            if text:
                parts.append(text)

        body_parts = []
        for p in tree.findall(".//body//p"):
            text = _get_element_text(p)
            if text:
                body_parts.append(text)

        if parts:
            full = "ABSTRACT:\n" + "\n".join(parts) + "\n\n"
        else:
            full = ""

        if body_parts:
            full += "MAIN TEXT:\n" + "\n\n".join(body_parts)

        return full.strip() if full.strip() else None
    except Exception as e:
        print(f"Error retrieving full text for {pmc_id}: {e}")
        return None


def _get_element_text(element) -> str:
    """Recursively get all text content from an XML element."""
    texts = []
    if element.text:
        texts.append(element.text)
    for child in element:
        texts.append(_get_element_text(child))
        if child.tail:
            texts.append(child.tail)
    return ''.join(texts)


def _construct_citation(article, doi) -> Tuple[str, str, str]:
    authors = article.findall(".//Author")
    author_list = []
    for author in authors:
        last = author.find("LastName")
        init = author.find("Initials")
        if last is not None and init is not None:
            author_list.append(f"{last.text} {init.text}")

    title_el = article.find(".//ArticleTitle")
    title = title_el.text if title_el is not None and title_el.text else "Unknown Title"

    journal_el = article.find(".//Journal/Title")
    journal = journal_el.text if journal_el is not None else "Unknown Journal"

    year_el = article.find(".//PubDate/Year")
    year = year_el.text if year_el is not None else "Unknown Year"

    volume_el = article.find(".//Volume")
    volume = volume_el.text if volume_el is not None else ""
    issue_el = article.find(".//Issue")
    issue = issue_el.text if issue_el is not None else ""
    pages_el = article.find(".//MedlinePgn")
    pages = pages_el.text if pages_el is not None else ""

    if author_list:
        authors_str = ", ".join(author_list[:6])
        if len(author_list) > 6:
            authors_str += ", et al."
    else:
        authors_str = "Unknown Authors"

    citation = f"{authors_str}. {title}. {journal}. {year}"
    if volume:
        citation += f";{volume}"
    if issue:
        citation += f"({issue})"
    if pages:
        citation += f":{pages}"
    citation += "."
    if doi:
        citation += f" doi: {doi}."

    return citation, journal, year


def retrieve_sources(api_key: str, search_terms: List[str],
                     retmax_per_term: int = 100,
                     per_term_limits: Optional[Dict[str, int]] = None,
                     progress_callback=None) -> List[Source]:
    """
    Retrieve sources from PubMed for all search terms.
    Deduplicates by DOI.
    """
    all_results = []
    for i, term in enumerate(search_terms):
        limit = retmax_per_term
        if per_term_limits and term in per_term_limits:
            limit = per_term_limits[term]
        results = search_pubmed(term, api_key, retmax=limit)
        all_results.extend(results)
        if progress_callback:
            progress_callback(f"Retrieved {len(results)} results for term {i+1}/{len(search_terms)}")
        sleep(0.35)  # NCBI rate limit

    # Deduplicate and build Source objects
    sources = []
    seen_dois = set()
    num = 1
    textless = []
    abless = []

    for result in all_results:
        doi = result.get('doi')
        if doi and doi in seen_dois:
            continue
        if doi:
            seen_dois.add(doi)

        # Attempt full text retrieval
        full_text = None
        if result.get('pmc_id'):
            full_text = get_full_text(result['pmc_id'], api_key)
            sleep(0.35)

        source = Source(
            number=num,
            title=result.get('title'),
            abstract=result.get('abstract'),
            pmid=result.get('pmid'),
            pmc_id=result.get('pmc_id'),
            citation=result.get('citation'),
            doi=doi,
            year=result.get('year'),
            journal=result.get('journal'),
            full_text=full_text
        )
        sources.append(source)
        if source.full_text is None:
            textless.append(num)
        if source.abstract is None:
            abless.append(num)
        num += 1

        if progress_callback:
            progress_callback(f"Processed source {num-1} (DOI dedup active)")

    return sources, textless, abless
