<!--
DETTE ER FORTSATT ET UTKAST. Alt merket [FYLL INN] er en plassholder jeg (Claude) ikke
har grunnlag for å fylle ut selv — jeg kjenner ikke Decon-X sin reelle produktkatalog
eller prising. "Fasit-eksempler" har nå en seksjon med EKTE saker hentet direkte fra
api.doffin.no/public/v2/search (2026-08-28, inkl. én tildeling vunnet av Decon-X
International AS selv), og en mindre seksjon med illustrasjoner for mønstre vi ikke
har ekte dekning for ennå (særlig mat-segmentet og underleverandør-mønsteret).

Kjør scripts/calibrate.py mot historiske CSV-år for å finne flere ekte saker, spesielt
bomtreff — de lærer modellen mest.

Dette dokumentet sendes verbatim inn i scoring-prompten (score_notices.py) som
kontekst for hver vurdering.
-->

# Relevansprofil: Decon-X

## Hva Decon-X selger

- **DX1** — [FYLL INN: kort presis beskrivelse — er dette en romdekontamineringsenhet
  (H2O2-tåke/damp), en mindre benkemontert sterilisator, eller noe annet? Kapasitet,
  typisk bruksområde (operasjonsrom, isolat, produksjonslokale)?]
- **DX3** — [FYLL INN: samme som over. Nevnt i sammenheng med Nofima-samarbeid, så
  antatt relevant for mat/akvakultur-segmentet — bekreft.]
- **H2O2-forbruksvarer** — konsumdel knyttet til maskinparken (påfyll/service). Følger
  installert base, ikke enkeltstående salg.
- [FYLL INN: andre produkter/tjenester — serviceavtaler, opplæring, utleie?]

## Segmenter

| Segment | Typisk kjøper | Typisk behov |
|---|---|---|
| Helse | Helseforetak, sykehus, private klinikker | Romdekontaminering av operasjonsrom, isolat, utstyrsvask |
| Dyrehelse | Oppdrettsanlegg, veterinærinstitusjoner, Mattilsynet | Biosikkerhet, smittevern mellom produksjonssykluser |
| Mat | Næringsmiddelprodusenter | Hygienesluser, produksjonslokale-dekontaminering |

## Typisk avtalestørrelse

[FYLL INN: prisklasse for en typisk DX1-avtale, en typisk DX3-avtale, og en typisk
rammeavtale/serviceavtale. Dette avgjør om en kunngjøring er "for liten til å bry seg
om" eller "for stor til å være realistisk uten partner" — begge er nyttige
diskvalifiserende signaler.]

## Diskvalifiserende kriterier (viktig — dette er der modellen bommer mest uten hjelp)

En kunngjøring er **IKKE** relevant, selv om CPV-koden matcher, når:

- Det er kjøp av **hånddesinfeksjon / håndsprit / overflatedesinfeksjonsmiddel til
  manuell bruk** — ikke maskinbasert romdekontaminering. (CPV 24455000 fanger begge,
  og de er ikke det samme markedet for Decon-X.)
- Det er en **generell forbruksvare-rammeavtale** for et helseforetak som dekker et
  bredt sortiment (bandasjer, sprit, engangsutstyr) der desinfeksjonsutstyr bare er én
  av mange linjer — for lav treffsannsynlighet til at Decon-X kan by konkurransedyktig
  som hovedleverandør.
- Det er **vaskemaskiner/desinfektorer for kirurgisk instrumentvask** (CPV kan
  overlappe 33191000) — dette er en annen produktkategori enn romdekontaminering.
- [FYLL INN: flere kjente diskvalifiserende mønstre fra egen erfaring — f.eks. minimum
  kontraktsverdi, geografi Decon-X ikke dekker, krav om spesifikke sertifiseringer
  Decon-X ikke har.]

## Hva som gjør en kunngjøring til et **direkte treff**

- Tittel/beskrivelse nevner romdekontaminering, H2O2-tåke/damp, biosikkerhetssluse,
  eller eksplisitt "desinfeksjonsrobot"/"desinfeksjonsenhet" for lokaler (ikke hender).
- Oppdragsgiver er i helse-, dyrehelse- eller matsegmentet fra `buyers.yaml`.
- Kontraktsstørrelse er i tråd med [FYLL INN: prisklasse].

## Hva som gjør en kunngjøring til en **underleverandør-posisjon**

- Det er en tjenestekunngjøring (CPV 90921000: desinfeksjons- og
  skadedyrbekjempelsestjenester) der en større aktør leverer helhetstjenesten, men
  utstyr/maskinvare kan leveres av en underleverandør.
- Rammeavtaler der Decon-X har reell sjanse som del-leverandør på én produktlinje,
  ikke som hovedleverandør på hele avtalen.

## Fasit-eksempler

> Formatet under er det scoring-promptet forventer: kort sak → riktig score/segment/flagg → **hvorfor**.

### Ekte saker (hentet direkte fra api.doffin.no/public/v2/search, 2026-08-28)

1. ✅ **"Sterilisator til sterilsentralen i Helse Bergen"** — Sykehusinnkjøp HF,
   id `2026-113098`, CPV 33191000/33191100. Erstatning av en Matachana
   130HPO-1-plasmasterilisator, planlagt kjøp tidlig 2027.
   → Score ~85, `helse`, `direkte_dx1` (forutsatt at DX1 faktisk konkurrerer mot
   plasmasterilisatorer for sterilsentraler — **[FYLL INN: bekreft]**).
   **Treff, men merk type**: dette er `ADVISORY_NOTICE`/`PLANNING`, altså en tidlig
   varsling før selve konkurransen lyses ut — verdifullt som forvarsel, ikke en
   kunngjøring man kan levere tilbud på ennå. Vurder om scoring-laget skal skille på
   `type`/`allTypes` for å flagge disse som "hold øye med" fremfor "svar nå".

2. ✅ **"1105601 UiO Livsvitenskap brukerutstyr K907 H2O2 desinfeksjonsutstyr"** —
   Statsbygg, id `2026-112718`, CPV 33191000/39330000/33100000/39300000. Tildelt
   kunngjøring — **vinner: Decon-X International AS**, egen bedrift.
   → Score ~95, `helse`, `direkte_dx1`. **Treff, bekreftet vunnet**: dette beviser at
   `lots[].winner` faktisk inneholder ekte, nyttige data — bruk dette mønsteret
   (H2O2 desinfeksjonsutstyr til forskningsbygg/laboratorium) som gullstandard for
   direkte treff.

3. ✅ **"1105601 UiO-OUS Livsvitenskap brukerutstyr K921.02 Autoklaver UiO"** —
   Statsbygg, id `2026-112929`, CPV 33191110/33191000/33191100/42710000-serien.
   Tildelt kunngjøring — vinner: **Heco Laboratorieutstyr AS** (konkurrent), to
   140L-autoklaver + én 450L gjennomgående autoklav til laboratoriebygg.
   → **[FYLL INN: var dette en reell mulighet for Decon-X, eller feil produktkategori
   (labo-autoklaver vs. romdekontaminering)? Om dere faktisk vurderte og tapte denne,
   er begrunnelsen her den viktigste linjen i hele dokumentet.]**

4. ✅ **"Desinfeksjonsservietter til helseforetakene i Norge"** — Sykehusinnkjøp HF,
   id `2026-113097`, CPV 33100000 (kun støy-koden), nasjonal rammeavtale for
   desinfeksjonsservietter til teknisk overflate, est. NOK 1,5M/år.
   → Score ~5, `none`. **Bomtreff**: manuelle servietter til overflate, ikke
   maskinbasert romdekontaminering — akkurat det diskvalifiserende kriteriet over
   beskriver, nå med en ekte sak.

5. ✅ **"Rammeavtale renholdsprodukter med opsjon for renholdsmaskiner og -roboter"**
   — Agder kollektivtransport AS m.fl. (27 kommuner/etater via OFA), id `2026-113550`,
   CPV inkluderer 24455000/39330000 blant ~40 brede renholds-koder, est. NOK 54M.
   → Score ~5, `none`. **Bomtreff**: en bred renholdsprodukt-rammeavtale der
   desinfeksjon er én linje av mange — akkurat mønsteret "generell
   forbruksvare-rammeavtale" i diskvalifiserende kriterier over, nå med ekte sak og
   ekte kontraktsstørrelse (NOK 54M, altså synlig stor CPV-treff som likevel skal
   scores lavt).

### Illustrasjoner (ikke ekte — dekker mønstre vi ikke har en ekte sak for ennå)

6. **"Biosikkerhetsutstyr til settefiskanlegg"** — oppdrettsselskap, CPV 39330000.
   → Score ~80, `dyrehelse`, `direkte_dx3`. **Treff**: biosikkerhet mellom
   produksjonssykluser i akvakultur er kjerneområdet for DX3 — **[FYLL INN: bytt ut
   med en ekte sak når dere finner én, DX3/Nofima-segmentet mangler fortsatt ekte
   eksempler]**.

7. **"Rammeavtale desinfeksjonstjenester — leveranse av utstyr og forbruksvarer"**
   — Sykehusinnkjøp HF, CPV 90921000 + 24455000. → Score ~65, `helse`,
   `underleverandor`. **Treff, men som del-leverandør**: helhetstjeneste der Decon-X
   realistisk kan by på utstyrs- og forbruksvare-delen, ikke hele avtalen.

[FYLL INN: flere ekte eksempler, spesielt for `mat`-segmentet og for
underleverandør-mønsteret — kjør scripts/calibrate.py mot flere historiske år og
buyers.yaml-treff for å finne flere.]
