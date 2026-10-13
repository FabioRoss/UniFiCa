"""Initial content for a fresh database: the Medicina sources and a starter
set of useful links and contacts (all editable from the admin panel)."""
from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Link, LinkGroup, Source

MED = "https://www.medicina.unifi.it/"
CAT = "Medicina e Chirurgia"

# (slug, name, path, interval minutes)
PAGES = [
    ("medicina-orario-lezioni", "Orario delle lezioni", "vp-94-orario-delle-lezioni.html", 30),
    ("medicina-esami-laurea", "Calendario esami di laurea", "vp-114-calendario-esami-di-laurea.html", 30),
    ("medicina-afp-1", "Tirocini AFP I anno", "vp-313-i-anno.html", 30),
    ("medicina-afp-2", "Tirocini AFP II anno", "vp-318-afp-ii-anno.html", 60),
    ("medicina-afp-3", "Tirocini AFP III anno", "vp-304-iii-anno.html", 60),
    ("medicina-afp-4", "Tirocini AFP IV anno", "vp-305-iv-anno.html", 60),
    ("medicina-afp-5", "Tirocini AFP V anno", "vp-306-v-anno.html", 30),
    ("medicina-tpv-6", "Tirocinio TPV VI anno", "vp-307-vi-anno.html", 30),
    ("medicina-ade", "Attività didattiche elettive (ADE)", "vp-118-attivita-didattiche-elettive.html", 60),
    ("medicina-calendario-esami", "Calendario esami", "vp-92-calendario-esami.html", 360),
    ("medicina-per-laurearsi", "Per laurearsi", "vp-17-per-laurearsi.html", 360),
    ("medicina-tutorato", "Tutorato", "vp-295-tutorato.html", 720),
    ("medicina-norme", "Norme e regolamenti", "vp-89-norme-e-regolamenti.html", 1440),
    ("medicina-organizzazione", "Organizzazione e verbali", "vp-108-organizzazione.html", 1440),
]


# ESSE3 exam-board settings per exam source (also used by `fetch-exams`)
EXAM_SOURCES: dict[str, dict[str, str]] = {
    "medicina-appelli": {"fac_id": "10267", "cds_ids": "11948,10670", "months_ahead": "6"},
}


def _maps(addr: str) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(addr + ", Firenze")


LINKS: list[tuple[str, str, list[dict]]] = [
    ("Segreterie e uffici", "Chi contattare per pratiche, carriera e tirocini", [
        dict(kind="contact", title="Segreteria studenti (Area Biomedica)",
             description="Documenti, certificati, problemi di carriera o tasse, immatricolazioni",
             email="segreteriastudenti.morgagni@unifi.it", url=MED + "vp-18-sedi-e-strutture.html",
             tags="certificati tasse carriera immatricolazione"),
        dict(kind="contact", title="Segreteria didattica CdLM Medicina",
             description="Convalide di carriere pregresse, regolamenti e propedeuticità",
             email="didmedicina@unifi.it", tags="convalide regolamenti propedeuticità"),
        dict(kind="contact", title="Ufficio Tirocini, Scuola di Scienze della Salute Umana",
             description="Libretti AFP, tirocini, consegne", email="tirocini.medicina@sc-saluteumana.unifi.it",
             location="NIC H3, I piano, stanza 120, Largo Brambilla 3", tags="AFP libretto tirocinio TPV"),
        dict(kind="contact", title="Scuola di Scienze della Salute Umana",
             email="scuola@sc-saluteumana.unifi.it", phone="+39 055 2751941",
             location="Largo Brambilla 3, 50134 Firenze", url="https://www.sc-saluteumana.unifi.it/"),
    ]),
    ("Servizi online", "Portali per esami, orari e tirocini", [
        dict(title="Lista appelli d'esame", url="https://studenti.unifi.it/ListaAppelliOfferta.do",
             description="Date degli appelli pubblicati", tags="esami appelli date"),
        dict(title="Sportello studenti (prenotazione esami)", url="https://studenti.unifi.it/",
             description="Iscrizione agli appelli, libretto, tasse (accesso con credenziali)",
             tags="esami prenotazione libretto tasse"),
        dict(title="Kairos: orari e aule", url="https://kairos.unifi.it/agendaweb",
             description="Orario delle lezioni e occupazione aule", tags="orario lezioni aule"),
        dict(title="TIROMED", url="https://sol.unifi.it/tiromed/login.jsp",
             description="Prenotazione dei reparti per tirocini e TPV", tags="tirocinio TPV reparti"),
        dict(title="Moodle e-learning", url="https://e-l.unifi.it", description="Materiali dei corsi",
             tags="moodle materiali slide"),
        dict(title="Course Catalogue", url="https://unifi.coursecatalogue.cineca.it/corsi/2026/5278",
             description="Programmi e docenti degli insegnamenti", tags="programmi insegnamenti docenti"),
        dict(title="Prenota un posto in biblioteca", url="https://www.sbafirenze.it/tools/posto-in-biblioteca",
             tags="biblioteca studio posto"),
    ]),
    ("Tutor e supporto", "Aiuto per studio, regolamenti e benessere", [
        dict(kind="contact", title="Tutor in itinere Medicina",
             description="Studenti tutor per regolamenti, modalità d'esame e metodo di studio",
             email="tutor-medicina-group@unifi.it", url="https://t.me/tutorintineremedicina",
             tags="tutor aiuto telegram"),
        dict(title="Tutorato didattico di Matematica", url=MED + "vp-295-tutorato.html", tags="tutor matematica"),
        dict(kind="contact", title="The Student's Voice", url="https://studentsvoice.unifi.it/",
             description="Segnalazioni e proposte degli studenti", email="studentsvoice@unifi.it"),
        dict(title="CeCoPs, consulenza psicologica",
             url="https://www.psicologia.unifi.it/vp-111-centro-di-servizi-di-ateneo-di-consulenza-psicologica-psicoterapia-e-ps.html",
             description="Supporto psicologico gratuito per studenti", tags="psicologo benessere ansia"),
        dict(title="UniFI Include", url="https://unifinclude.unifi.it/",
             description="Servizi per studenti con disabilità e DSA, studenti atleti", tags="disabilità DSA"),
    ]),
    ("Aule e sedi", "Dove si fa lezione (area Careggi)", [
        dict(kind="contact", title="Aula A e Aula B, Dip. Scienze Biomediche \"Mario Serio\"",
             location="Viale G. B. Morgagni 50", url=_maps("Viale Giovanni Battista Morgagni 50")),
        dict(kind="contact", title="Aula Grande e Aula Piccola del CUBO (Padiglione 27)",
             location="Viale Pieraccini 6", url=_maps("Viale Gaetano Pieraccini 6")),
        dict(kind="contact", title="Aule 201 e 203, Dip. Matematica \"Ulisse Dini\"",
             location="Viale G. B. Morgagni 67/A", url=_maps("Viale Giovanni Battista Morgagni 67/A")),
        dict(kind="contact", title="Aula Clinica Medica III (Padiglione 13)",
             location="Via San Luca 5", url=_maps("Via San Luca 5")),
        dict(kind="contact", title="Aula A Scienze Fisiologiche",
             location="Viale G. B. Morgagni 63", url=_maps("Viale Giovanni Battista Morgagni 63")),
        dict(kind="contact", title="Biblioteca Biomedica", location="Careggi, dopo il NIC sulla sinistra",
             url="http://www.sba.unifi.it/CMpro-l-s-10.html", tags="biblioteca studio prestito"),
    ]),
    ("Vita universitaria", "Mense, alloggi, borse e siti ufficiali", [
        dict(title="DSU Toscana", url="http://www.dsu.toscana.it",
             description="Borse di studio, alloggi, mense", tags="borsa di studio alloggi"),
        dict(title="Mense universitarie Firenze", url="http://www.dsu.toscana.it/it/ristorazione/mense/firenze/",
             tags="mensa pranzo cena"),
        dict(title="Aule studio DSU", url="http://www.dsu.toscana.it/it/alloggi/aule_studio/", tags="studio aule"),
        dict(title="Sito del Corso di Laurea in Medicina e Chirurgia", url=MED),
        dict(title="Canale Telegram UniFI", url="https://t.me/unifirenze", tags="telegram ateneo"),
    ]),
]


def seed(db: Session) -> None:
    if not db.scalar(select(func.count()).select_from(Source)):
        db.add(Source(
            slug="medicina-news", name="News Medicina e Chirurgia", category=CAT, kind="news",
            parser="unifi_news", url=MED + "news.html",
            archive_url=MED + "index.php?module=NEWSpro&func=list&filter=arch&catid=1",
            interval_minutes=10, position=0,
        ))
        for i, (slug, name, path, interval) in enumerate(PAGES, start=1):
            db.add(Source(slug=slug, name=name, category=CAT, kind="page", parser="page",
                          url=MED + path, interval_minutes=interval, position=i))
        # ESSE3 public exam board: school "Scienze della Salute Umana" (10267),
        # courses B240 (11948) and B120 (10670) Medicina e Chirurgia.
        db.add(Source(
            slug="medicina-appelli", name="Appelli d'esame Medicina", category=CAT, kind="exams",
            parser="esse3_appelli", url="https://studenti.unifi.it/ListaAppelliOfferta.do",
            config=dict(EXAM_SOURCES["medicina-appelli"]),
            interval_minutes=60, track_attachments=False, position=len(PAGES) + 1,
        ))
    if not db.scalar(select(func.count()).select_from(LinkGroup)):
        for gi, (name, desc, links) in enumerate(LINKS):
            g = LinkGroup(name=name, description=desc, position=gi)
            for li, link in enumerate(links):
                g.links.append(Link(position=li, **{"kind": "link", **link}))
            db.add(g)
    db.commit()
