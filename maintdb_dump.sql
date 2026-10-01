--
-- PostgreSQL database dump
--

\restrict ZVM1XbUDAkenyboNWL9ReshLhbJ2lJGzm5KGKxHouiuhMKA6KNgqouKJrsRbG9U

-- Dumped from database version 17.10 (Homebrew)
-- Dumped by pg_dump version 17.10 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: asset_batteries; Type: TABLE; Schema: public; Owner: lukesevenish
--

CREATE TABLE public.asset_batteries (
    id integer NOT NULL,
    asset_id text NOT NULL,
    battery_number integer NOT NULL,
    description text,
    part_number text,
    replacement_interval_days integer
);


ALTER TABLE public.asset_batteries OWNER TO lukesevenish;

--
-- Name: asset_batteries_id_seq; Type: SEQUENCE; Schema: public; Owner: lukesevenish
--

CREATE SEQUENCE public.asset_batteries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.asset_batteries_id_seq OWNER TO lukesevenish;

--
-- Name: asset_batteries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lukesevenish
--

ALTER SEQUENCE public.asset_batteries_id_seq OWNED BY public.asset_batteries.id;


--
-- Name: asset_peripheral_equipment; Type: TABLE; Schema: public; Owner: lukesevenish
--

CREATE TABLE public.asset_peripheral_equipment (
    id integer NOT NULL,
    asset_id text NOT NULL,
    equip_number integer NOT NULL,
    name text,
    make text,
    model text,
    serial_number text
);


ALTER TABLE public.asset_peripheral_equipment OWNER TO lukesevenish;

--
-- Name: asset_peripheral_equipment_id_seq; Type: SEQUENCE; Schema: public; Owner: lukesevenish
--

CREATE SEQUENCE public.asset_peripheral_equipment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.asset_peripheral_equipment_id_seq OWNER TO lukesevenish;

--
-- Name: asset_peripheral_equipment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lukesevenish
--

ALTER SEQUENCE public.asset_peripheral_equipment_id_seq OWNED BY public.asset_peripheral_equipment.id;


--
-- Name: assets; Type: TABLE; Schema: public; Owner: lukesevenish
--

CREATE TABLE public.assets (
    asset_id text NOT NULL,
    asset_code text NOT NULL,
    department_code character(1),
    sequence_number text,
    display_name text,
    short_name text,
    equipment_category text,
    primary_function text,
    manufacturer text,
    model text,
    serial_number text,
    control_type text,
    build_year integer,
    distributor text,
    distributor_email text,
    distributor_phone text,
    vendor_contacts text,
    facility text,
    area_cell text,
    commission_date date,
    asset_status text,
    planned_pm_interval_days integer,
    installation_notes text,
    known_quirks text,
    special_tooling text,
    reference_document text,
    template_version text,
    registry_created_by text,
    registry_creation_date timestamp with time zone,
    final_lock_date date,
    approved_by text,
    folder_path text
);


ALTER TABLE public.assets OWNER TO lukesevenish;

--
-- Name: employees; Type: TABLE; Schema: public; Owner: lukesevenish
--

CREATE TABLE public.employees (
    employee_id text NOT NULL,
    name text NOT NULL,
    role text
);


ALTER TABLE public.employees OWNER TO lukesevenish;

--
-- Name: jobs; Type: TABLE; Schema: public; Owner: lukesevenish
--

CREATE TABLE public.jobs (
    job_no text NOT NULL,
    part_no text,
    customer text,
    order_qty integer,
    due_date date,
    est_setup_hours numeric(6,2),
    est_run_hours numeric(6,2),
    status text
);


ALTER TABLE public.jobs OWNER TO lukesevenish;

--
-- Name: labor_tickets; Type: TABLE; Schema: public; Owner: lukesevenish
--

CREATE TABLE public.labor_tickets (
    ticket_id integer NOT NULL,
    employee_id text,
    job_no text,
    machine_id text,
    op_code text,
    op_desc text,
    time_in timestamp with time zone,
    time_out timestamp with time zone,
    setup_hours numeric(6,2),
    run_hours numeric(6,2),
    qty_good integer,
    qty_scrap integer
);


ALTER TABLE public.labor_tickets OWNER TO lukesevenish;

--
-- Name: labor_tickets_ticket_id_seq; Type: SEQUENCE; Schema: public; Owner: lukesevenish
--

CREATE SEQUENCE public.labor_tickets_ticket_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.labor_tickets_ticket_id_seq OWNER TO lukesevenish;

--
-- Name: labor_tickets_ticket_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: lukesevenish
--

ALTER SEQUENCE public.labor_tickets_ticket_id_seq OWNED BY public.labor_tickets.ticket_id;


--
-- Name: work_centers; Type: TABLE; Schema: public; Owner: lukesevenish
--

CREATE TABLE public.work_centers (
    machine_id text NOT NULL,
    machine_name text NOT NULL,
    department text NOT NULL
);


ALTER TABLE public.work_centers OWNER TO lukesevenish;

--
-- Name: asset_batteries id; Type: DEFAULT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.asset_batteries ALTER COLUMN id SET DEFAULT nextval('public.asset_batteries_id_seq'::regclass);


--
-- Name: asset_peripheral_equipment id; Type: DEFAULT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.asset_peripheral_equipment ALTER COLUMN id SET DEFAULT nextval('public.asset_peripheral_equipment_id_seq'::regclass);


--
-- Name: labor_tickets ticket_id; Type: DEFAULT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.labor_tickets ALTER COLUMN ticket_id SET DEFAULT nextval('public.labor_tickets_ticket_id_seq'::regclass);


--
-- Data for Name: asset_batteries; Type: TABLE DATA; Schema: public; Owner: lukesevenish
--

COPY public.asset_batteries (id, asset_id, battery_number, description, part_number, replacement_interval_days) FROM stdin;
1	A-L001	1	Servo/Memory	LR20  D cell 8x	365
2	A-L001	2	Control	A98L-0031-0028	720
3	A-L002	1	Servo/Memory	LR20  D 8X	365
4	A-L002	2	Control	Q6BAT	365
5	A-L003	1	Servo/Memory	LR20  D 4X	365
6	A-L003	2	Control	A98L-0031-0028	365
7	A-L004	1	Servo/Memory	LR20  D 4X	365
8	A-L004	2	\N	A98L-0031-0028	365
9	A-L005	1	Servo/Drive	BR-2/3 AG	720
10	A-L006	1	Servo/Memory	LR20  D 8X	365
11	A-L006	2	Drive	BR-2/3 AG	720
12	A-L007	1	Servo/Memory	\N	365
13	A-L007	2	Control	A98L-0031-0028	720
14	A-L009	1	Drive	BR-2/3 AG	365
15	A-L010	1	Servo/Memory	4 D Cell	368
16	A-L010	2	Control	A98L-0031-0026	365
17	A-L011	1	Drive	BR 2/3 AG	365
18	A-L012	1	Drive	BR-2/3 AG	365
19	A-L013	1	Drive	BR-2/3 AG (RD-PLC13)	365
20	A-L014	1	Drive	BR-2/3 AG	365
21	A-L015	1	Servo/Memory	3 D Cell	365
22	A-L016	1	Servo/Memory	3 D Cell	365
23	A-M001	1	Servo/Memory	LR20  D 4X	365
24	A-M001	2	Control	A98L-0031-0028	720
25	A-M002	1	Drive	BR-2/3 AG	365
26	A-M002	2	Control	RD-PLC23-FDK	365
27	A-M003	1	Drive	BR-2/3 AG	365
28	A-M003	2	Control	RD-PLC23-FDK	365
29	A-M004	1	Drive	BR-2/3 AG	365
30	A-M004	2	Control	RD-PLC23-FDK	365
31	A-M005	1	Servo	4 D Cell	365
32	A-M005	2	Drive	2x  BR-2/3 AG  	365
33	A-M006	1	Servo/Memory	10 D Cell	365
34	A-M006	2	Drive	BR-2/3 AG	365
35	A-M007	1	Servo/Memory	4 D Cell	365
36	A-M007	2	Control	A98L-0031-0026	365
37	A-M008	1	Servo/Memory	4 D Cell	365
38	A-M008	2	Control	2 D Cell	365
39	A-M009	1	Servo/Memory	4 D Cell	365
40	A-M009	2	Drive	BR-2/3 AG	365
41	A-S003	2	Control	A98L-0031-0028	365
\.


--
-- Data for Name: asset_peripheral_equipment; Type: TABLE DATA; Schema: public; Owner: lukesevenish
--

COPY public.asset_peripheral_equipment (id, asset_id, equip_number, name, make, model, serial_number) FROM stdin;
1	A-L001	1	Bar Loader	Edge	Rebel 102	T1202425989
2	A-L001	2	HP Pump	LNS/Chip Blaster	F-30	23C02F00661
3	A-L001	3	Mist Collector	Aeroex	Mist Fit 550	23-0494
4	A-L002	1	Bar loader	IEMCA 	Kid 80	022104QA01
5	A-L002	2	HP Pump	LNS/Chip Blaster	V-40	23C03V00479
6	A-L002	3	Mist Collector	Aeroex	Mist Fit 350	22-0111
7	A-L003	1	Bar loader	LNS	QLS80 S2	15002001255
8	A-L003	2	Chip Conveyor	LNS	57519015	13575107984
9	A-L004	1	Bar Loader	LNS	QLS80 S2	15002002254
10	A-L004	2	Chip Conveyor	LNS	57519019	13575105903
11	A-L004	3	Mist Collector	Aeroex	Mist Fit 350	22-0111
12	A-L006	1	Bar Loader	LNS	Quickload	18861
13	A-L006	2	H/P Pump	Chip Blaster	V-40	23C03V00479
14	A-L006	3	Mist Collector	Aeroex	Mist Fit 350	22-0111
15	A-L007	1	Bar loader	LNS	QLS80 S2	27049207
16	A-L007	2	Chiller	Turmoil	OCO-75	15878-13
17	A-L007	3	Mist Collector	Aeroex	Mist Fit 350	22-0111
18	A-L008	1	Bar Loader	LNS	QLS80 S2	300638
19	A-L009	1	Mist Collector	Royal 	Royal Mist 750	\N
20	A-L010	1	Mist Collector	Losma	Darwin 600 Clipper 10	\N
21	A-L011	1	Mist Collector	Aerocology	\N	\N
22	A-L012	1	Mist Collector	Losma	Darwin 2000	\N
23	A-L013	1	Mist Collector	Donaldson	\N	\N
24	A-L014	1	Mist Collector	Aerocology	\N	\N
25	A-L015	1	Bar Loader	Iemca	VIP80E II	021151QA02
26	A-L015	2	Mist Collector	Losma	Darwin 2000	\N
27	A-L016	1	Mist Collector	Aercology	\N	\N
28	A-M001	1	High Pressure Pump	MP Systems	ATV-R8	P241117A
29	A-M001	2	Chip Conveyor	LNS	57109046	13571000780
30	A-M001	3	Mist Collector	FOX	HM2 700	\N
31	A-M002	1	Mist Collector	Losma	Darwin 600  Clipper 10	-
32	A-M003	1	Mist Collector	Losma	Darwin 600 Clipper 10	-
33	A-M005	1	Mist Collector	Losma	Darwin 600 Clipper 10	\N
34	A-M006	1	HP Pump	Chip Blaster	JV8	5357
35	A-M006	2	Mist Collector	Chip Blaster	Mist Blaster	5358
36	A-M007	1	Mist Collector	Losma	Darwin 600 Clipper 10	\N
37	A-M008	1	Chip Conveyor	Turbo Microfine	6598-8044	359024
38	A-M008	2	Pallet Pool  Shared	Mori Seiki	\N	\N
39	A-M009	1	Chip Conveyor	Turbo Microfine	6598-8024	343880
40	A-M009	2	Pallet Pool  Shared	Mori Seiki	\N	\N
41	A-S001	1	Bar Loader	FMB	Micromag 20	33-320867 R2117865
42	A-S001	2	High Pressure	NETC 	Pressure Tech PT1000-8W	000030
43	A-S001	3	Mist Collector	Tri-Mist	850 G2	24482
44	A-S002	1	Bar Loader	LNS	Alpha 552	15055200085
45	A-S002	2	High Pressure	NETC	NJ1759	011220
46	A-S002	3	Chiller	Daikin	AKZC358-CP	8200378
47	A-S003	1	Bar Loader	LNS	GT 326-E	15232000987
48	A-S003	2	High Pressure	NETC	NJ1750	011932
49	A-S003	3	Mist Collector	Tri-Mist	850 G2	24482
50	A-S004	1	Bar Loader	FMB	Turbo 3-26	62-264920 R:1977285
51	A-S004	2	HP Pump	NETC	Pressure Tech PT1000-8	000520
52	A-S004	3	Chip Conveyor	LNS	MH500	13570102794
53	A-S005	1	Bar Loader	LNS	GT 326-E	15232001114
54	A-S005	2	HP Pump	NETC	J1750	012003
55	A-S005	3	Mist Collector	Tri-Mist	850 G2	25437
56	A-S006	1	Bar Loader	LNS	Express 220	135398
57	A-S006	2	High Pressure	NETC	J1750	010664
58	A-S006	3	Mist Collector	Losma	Darwin 600	5158
59	A-S007	1	Bar Loader	LNS	Express 326 S2	101180-01
60	A-S007	2	High Pressure	NETC	J1750	010662
61	A-S007	3	Mist Collector	Aercology	\N	\N
\.


--
-- Data for Name: assets; Type: TABLE DATA; Schema: public; Owner: lukesevenish
--

COPY public.assets (asset_id, asset_code, department_code, sequence_number, display_name, short_name, equipment_category, primary_function, manufacturer, model, serial_number, control_type, build_year, distributor, distributor_email, distributor_phone, vendor_contacts, facility, area_cell, commission_date, asset_status, planned_pm_interval_days, installation_notes, known_quirks, special_tooling, reference_document, template_version, registry_created_by, registry_creation_date, final_lock_date, approved_by, folder_path) FROM stdin;
A-L001	L001	L	001	L001-TA-30-YS-640+GL20II	L001-TA-30-YS-640+GL20II	Lathe	Machining	CMZ	TA-30-YS-640+GL20II	2245	FANUC 32i B	2023	Great Lakes Machinery	jon@glmincny.com     sean@glmincny.com	716.684.4100	Sean Trabert- President\nJon Mesch- VP/Service Mgr\nMike- Parts	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-07 10:49:45.762-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L001-TA-30-YS-640+GL20II
A-L002	L002	L	002	L002-B438-Y2	L002-B438-Y2	Lathe	Machining	Eurotech Elite	B438-Y2	14896	M700	2020	Great Lakes Machinery	jon@glmincny.com     sean@glmincny.com	716.684.4100	Sean Trabert- President\nJon Mesch- VP/Service Mgr\nMike- Parts	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-07 11:06:17.58-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L002-B438-Y2
A-L003	L003	L	003	L003-Lynx-2100LSYA	L003-Lynx -2100LSYA	Lathe	Machining	Doosan	Lynx 2100LSYA	ML0405-000344	Fanuc 32i	2022	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-08 06:05:13.926-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L003-Lynx-2100LSYA
A-L004	L004	L	004	L004-Puma-TT1800SY	L004-Puma-TT1800SY	Lathe	Machining	Doosan	Puma TT1800SY	ML0177-001496	Fanuc 32i	2022	Syracuse Supply	parts@syrpupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-08 06:08:17.25-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L004-Puma-TT1800SY
A-L005	L005	L	005	L005-BL05	L005-BL05	Lathe	\N	Mori Seiki	BL05	22	Fanuc 18	1995	DMG Mori	\N	\N	DMG Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-08 06:48:58.541-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L005-BL05
A-L006	L006	L	006	L006-SL-25MC	L006-SL-25MC	Lathe	\N	Mori Seiki	SL-25MC	1193	Fanuc 18	1995	DMG Mori	jon@glmincny.com     sean@glmincny.com	716.684.4100	DMG Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-08 06:52:34.557-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L006-SL-25MC
A-L007	L007	L	007	L007-Super-Precision-T42	L007-Super-Precision-T42	Lathe	\N	Hardinge	Super-Precision-T42	CQ135SP	Fanuc 31i  A	2012	Great Lakes Machinery	jon@glmincny.com     sean@glmincny.com	716.684.4100	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-08 06:57:38.691-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L007-Super-Precision-T42
A-L008	L008	L	008	L008-BND42C	L008-BND42C	Lathe	\N	Miyano	BND42C	BD60067C	Fanuc 21	\N	Excel Machine Technologies	parts@emtcnc.com	585.426.1911	Jason Boyle- President\nJeremey Shamp- VP\nJason Herman- Service Mgr\nEvin Ager- Parts	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-08 10:02:59.378-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L008-BND42C
A-L009	L009	L	009	L009-CL-20	L009-CL-20	Lathe	\N	Mori Seiki	CL-20	1813	Fanuc 18	1996	DMG-Mori	DMG Mori Portal	\N	Dmg Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 05:13:04.777-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L009-CL-20
A-L010	L010	L	010	L010-DT	L010-DT	Lathe	\N	Mori Seiki	DT	DT203GK0067	Fanuc 31i	2007	DMG-Mori	DMG Mori Portal	\N	DMG Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 05:15:02.953-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L010-DT
A-L011	L011	L	011	L011-GN4	L011-GN4	Lathe	\N	Ocean	GN4	GN4037	Fanuc O-T	1999	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 05:45:32.529-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L011-GN4
A-L012	L012	L	012	L012-GT	L012-GT	Lathe	\N	Hardinge	GT	MG468	Fanuc 21	\N	Morris Great Lakes	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 05:46:53.329-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L012-GT
A-L013	L013	L	013	L013-GT	L013-GT	Lathe	\N	Hardinge	GT	MG427	Fanuc 21	\N	Morris Great Lakes	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 05:48:07.554-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L013-GT
A-L014	L014	L	014	L014-GT	L014-GT	Lathe	\N	Hardinge	GT	MG283	Fanuc 21	\N	Morris Great Lakes	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 05:49:06.12-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L014-GT
A-L015	L015	L	015	L015-BND-34T	L015-BND-34T	Lathe	\N	Miyano	BND-34T	BN30541T	FANUC 18	\N	Excel Machine Technologies	parts@emtcnc.com	585.426.1911	Jason Boyle- President  jasonb@emtcnc.com\nJeremy Shamp- VP    jeremeys@emtcnc.com\nJason Herman- Service Mgr    jasonh@emtcnc.com\nEvin Ager- Parts   evina@emtcnc.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-12 03:34:00.912-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L015-BND-34T
A-L016	L016	L	016	L016-BNC-12C	L016-BNC-12C	Lathe	\N	Miyano	BNC-12C	10221C	Fanuc 18	\N	Excel Machine Technologies	parts@emtcnc.com	585.426.1911	Jason Boyle- President  jasonb@emtcnc.com\nJeremy Shamp- VP    jeremeys@emtcnc.com\nJason Herman- Service Mgr    jasonh@emtcnc.com\nEvin Ager- Parts   evina@emtcnc.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-12 03:35:39.472-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-L016-BNC-12C
A-M001	M001	M	001	M001-DVF5000	M001-DVF5000	Mill	\N	Doosan	DVF5000	MV0111-001246	Fanuc 32i B	2024	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-08 10:09:22.767-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M001-DVF5000
A-M002	M002	M	002	M002-DMV4020	M002-DMV4020	Mill	\N	Doosan	DMV 4020	AV5E-2423	FANUC 21i MB	2005	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 04:17:30.668-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M002-DMV-4020
A-M003	M003	M	003	M003-DMV 4020	M003-DMV 4020	Mill	\N	Doosan	DMV 4020	AV5E-2184	Fanuc 21i MB	2005	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 04:22:11.864-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M003-DMV-4020
A-M004	M004	M	004	M004-DMV 4020	M004-DMV 4020	Mill	\N	Doosan	DMV 4020	AV5E-2278	Fanuc 21i MB	2005	Syracuse Supply	parts@syrupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 04:26:11.033-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M004-DMV-4020
A-M005	M005	M	005	M005-SV40	M005-SV40	Mill	\N	Mori Seiki	SV40	118	Fanuc 18	1997	DMG-Mori	DMG Mori portal	\N	DMG Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 04:42:18.737-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M005-SV40
A-M006	M006	M	006	M006-NV5000	M006-NV5000	Mill	\N	Mori Seiki	NV5000	NV501DA1543	Fanuc 21	2004	DMG-Mori	DMG Mori Portal	\N	DMG Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-11 04:44:43.654-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M006-NV5000
A-M007	M007	M	007	M007-DV	M007-DV	Mill	\N	Mori Seiki	DV	DV005GJ1114	Fanuc	2007	DMG-Mori	DMG Mori Portal	\N	DMG Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-12 03:37:35.326-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M007-DV
A-M008	M008	M	008	M008-SH403	M008-SH403	Mill	\N	Mori Seiki	SH403	SH400BD1657	Fanuc 21	\N	DMG-Mori	DMG Mori Portal	\N	DMG Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-12 03:39:59.902-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M008-SH403
A-M009	M009	M	009	M009-SH400	M009-SH400	Mill	\N	Mori Seiki	SH400	254	Fanuc 18	\N	DMG-Mori	DMG Mori Portal	\N	DMG Mori Portal	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-12 03:41:50.387-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-M009-SH400
A-S001	S001	S	001	S001-SW-12RII	S001-SW-12RII	Swiss	\N	Star	SW-12RII	0447	Fanuc 31i B	2022	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-13 06:26:42.306-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-S001-SW-12RII
A-S002	S002	S	002	S002-ST38	S002-ST38	Swiss	\N	Star 	ST38	0145	Fanuc 30i A	2013	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-13 06:29:15.873-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-S002-ST38
A-S003	S003	S	003	S003-SB-20R G	S003-SB-20R G	Swiss	\N	Star	SB-20R G	3511	Fanuc Oi-TF	2018	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-13 06:32:16.307-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-S003-SB-20R G
A-S004	S004	S	004	S004-SR20R IV type A	S004-SR20R IV type A	Swiss	\N	Star	SR20R IV type A	837	Fanuc 31i B	2022	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-14 05:04:44.943-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-S004-SR20R IV type A
A-S005	S005	S	005	S005-SB20R type G	S005-SB20R type G	Swiss	\N	Star	SB20R type G	4473	Fanuc Oi-TF	2018	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-14 05:06:49.834-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-S005-SB20R type G
A-S006	S006	S	006	S006-SR20R III	S006-SR20R III	Swiss	\N	Star	SR20R III	0608	Fanuc 300-is A	2008	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-14 06:04:16.645-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-S006-SR20R III
A-S007	S007	S	007	S007-SR20R III	S007-SR20R III	Swiss	\N	Star	SR20R III	0490	Fanuc 300 is A	2008	Syracuse Supply	parts@syrsupply.com	716.893.3643	Kevin McCarthy- President/Sales\nStefan Marsh- Industrial Sales\nMark Fuss- Service Mgr	\N	\N	\N	\N	\N	\N	\N	\N	\N	1.0	\N	2026-05-14 06:09:33.392-04	\N	\N	/Users/lukesevenish/Documents/Claude/Projects/MaintDB/Maintenance_DB/A-S007-SR20R III
\.


--
-- Data for Name: employees; Type: TABLE DATA; Schema: public; Owner: lukesevenish
--

COPY public.employees (employee_id, name, role) FROM stdin;
\.


--
-- Data for Name: jobs; Type: TABLE DATA; Schema: public; Owner: lukesevenish
--

COPY public.jobs (job_no, part_no, customer, order_qty, due_date, est_setup_hours, est_run_hours, status) FROM stdin;
\.


--
-- Data for Name: labor_tickets; Type: TABLE DATA; Schema: public; Owner: lukesevenish
--

COPY public.labor_tickets (ticket_id, employee_id, job_no, machine_id, op_code, op_desc, time_in, time_out, setup_hours, run_hours, qty_good, qty_scrap) FROM stdin;
\.


--
-- Data for Name: work_centers; Type: TABLE DATA; Schema: public; Owner: lukesevenish
--

COPY public.work_centers (machine_id, machine_name, department) FROM stdin;
L001	TA-30-YS-640+GL20II	Lathe
L002	B438-Y2	Lathe
L003	Lynx 2100LSYA	Lathe
L004	Puma TT1800SY	Lathe
L005	BL05	Lathe
L006	SL-25MC	Lathe
L007	Super Precision T42	Lathe
L008	BND42C	Lathe
L009	CL-20	Lathe
L010	DT	Lathe
L011	GN4	Lathe
L012	GT	Lathe
L013	GT	Lathe
L014	GT	Lathe
L015	BND-34T	Lathe
L016	BNC-12C	Lathe
M001	DVF5000	Mill
M002	DMV 4020	Mill
M003	DMV 4020	Mill
M004	DMV 4020	Mill
M005	SV40	Mill
M006	NV5000	Mill
M007	DV	Mill
M008	SH403	Mill
M009	SH400	Mill
S001	SW-12RII	Swiss
S002	ST38	Swiss
S003	SB-20R G	Swiss
S004	SR20R IV type A	Swiss
S005	SB20R type G	Swiss
S006	SR20R III	Swiss
S007	SR20R III	Swiss
E001	Saw / Equipment	Support
Q001	QC Station	QC
\.


--
-- Name: asset_batteries_id_seq; Type: SEQUENCE SET; Schema: public; Owner: lukesevenish
--

SELECT pg_catalog.setval('public.asset_batteries_id_seq', 41, true);


--
-- Name: asset_peripheral_equipment_id_seq; Type: SEQUENCE SET; Schema: public; Owner: lukesevenish
--

SELECT pg_catalog.setval('public.asset_peripheral_equipment_id_seq', 61, true);


--
-- Name: labor_tickets_ticket_id_seq; Type: SEQUENCE SET; Schema: public; Owner: lukesevenish
--

SELECT pg_catalog.setval('public.labor_tickets_ticket_id_seq', 1, false);


--
-- Name: asset_batteries asset_batteries_pkey; Type: CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.asset_batteries
    ADD CONSTRAINT asset_batteries_pkey PRIMARY KEY (id);


--
-- Name: asset_peripheral_equipment asset_peripheral_equipment_pkey; Type: CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.asset_peripheral_equipment
    ADD CONSTRAINT asset_peripheral_equipment_pkey PRIMARY KEY (id);


--
-- Name: assets assets_pkey; Type: CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.assets
    ADD CONSTRAINT assets_pkey PRIMARY KEY (asset_id);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (employee_id);


--
-- Name: jobs jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.jobs
    ADD CONSTRAINT jobs_pkey PRIMARY KEY (job_no);


--
-- Name: labor_tickets labor_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.labor_tickets
    ADD CONSTRAINT labor_tickets_pkey PRIMARY KEY (ticket_id);


--
-- Name: work_centers work_centers_pkey; Type: CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.work_centers
    ADD CONSTRAINT work_centers_pkey PRIMARY KEY (machine_id);


--
-- Name: idx_asset_batteries_asset_battery; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_asset_batteries_asset_battery ON public.asset_batteries USING btree (asset_id, battery_number);


--
-- Name: idx_asset_pe_asset_equip; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_asset_pe_asset_equip ON public.asset_peripheral_equipment USING btree (asset_id, equip_number);


--
-- Name: idx_assets_asset_code; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_assets_asset_code ON public.assets USING btree (asset_code);


--
-- Name: idx_assets_asset_status; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_assets_asset_status ON public.assets USING btree (asset_status);


--
-- Name: idx_assets_dept_code; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_assets_dept_code ON public.assets USING btree (department_code);


--
-- Name: idx_assets_equipment_category; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_assets_equipment_category ON public.assets USING btree (equipment_category);


--
-- Name: idx_jobs_status; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_jobs_status ON public.jobs USING btree (status);


--
-- Name: idx_labor_tickets_employee_id; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_labor_tickets_employee_id ON public.labor_tickets USING btree (employee_id);


--
-- Name: idx_labor_tickets_job_no; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_labor_tickets_job_no ON public.labor_tickets USING btree (job_no);


--
-- Name: idx_labor_tickets_machine_id; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_labor_tickets_machine_id ON public.labor_tickets USING btree (machine_id);


--
-- Name: idx_labor_tickets_time_in; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_labor_tickets_time_in ON public.labor_tickets USING btree (time_in);


--
-- Name: idx_lt_active; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_lt_active ON public.labor_tickets USING btree (time_in) WHERE (time_out IS NULL);


--
-- Name: idx_lt_op_code; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_lt_op_code ON public.labor_tickets USING btree (op_code);


--
-- Name: idx_lt_op_machine; Type: INDEX; Schema: public; Owner: lukesevenish
--

CREATE INDEX idx_lt_op_machine ON public.labor_tickets USING btree (op_code, machine_id);


--
-- Name: asset_batteries asset_batteries_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.asset_batteries
    ADD CONSTRAINT asset_batteries_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.assets(asset_id);


--
-- Name: asset_peripheral_equipment asset_peripheral_equipment_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.asset_peripheral_equipment
    ADD CONSTRAINT asset_peripheral_equipment_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.assets(asset_id);


--
-- Name: labor_tickets labor_tickets_employee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.labor_tickets
    ADD CONSTRAINT labor_tickets_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id);


--
-- Name: labor_tickets labor_tickets_job_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.labor_tickets
    ADD CONSTRAINT labor_tickets_job_no_fkey FOREIGN KEY (job_no) REFERENCES public.jobs(job_no);


--
-- Name: labor_tickets labor_tickets_machine_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: lukesevenish
--

ALTER TABLE ONLY public.labor_tickets
    ADD CONSTRAINT labor_tickets_machine_id_fkey FOREIGN KEY (machine_id) REFERENCES public.work_centers(machine_id);


--
-- PostgreSQL database dump complete
--

\unrestrict ZVM1XbUDAkenyboNWL9ReshLhbJ2lJGzm5KGKxHouiuhMKA6KNgqouKJrsRbG9U

