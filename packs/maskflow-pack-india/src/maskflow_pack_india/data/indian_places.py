"""Bundled Indian place-name gazetteer for INDIAN_ADDRESS L1 matching
(../gazetteer.py) -- states/UTs + top cities/towns by population.

INDIAN_STATE_UT_NAMES is the same 36-entry list this pack already used for
PIN_CODE's context keywords (moved here from __init__.py, re-exported there
unchanged so that registration is unaffected).

INDIAN_CITIES: 368 city/town names, fetched 2026-08-26 from Wikipedia's
"List of cities in India by population" (https://en.wikipedia.org/wiki/
List_of_cities_in_India_by_population, CC-BY-SA 4.0 + GFDL -- attribution:
Wikipedia contributors, linked article + edit history), merging its
million-plus-cities map labels with its 100,000-1,000,000 population table.
Short of the work order's "top-500" target -- 368 is what the article's two
population tables actually cover after dedup; see the L1 report. A small
number of alternate-spelling near-duplicates from the source article
(Amaravathi/Amaravati, Hubballi-Dharwad/Hubli-Dharwad, Kalyan-Dombivali/
Kalyan-Dombivli, ...) are kept as separate entries deliberately -- both
spellings are real-world usage and matching either is the point of a
gazetteer.

INDIAN_PLACE_NAMES is the flat set gazetteer.py's automaton is actually
built from -- cities plus Title-Case state/UT names, deduplicated.
"""

from __future__ import annotations

INDIAN_STATE_UT_NAMES: tuple[str, ...] = (
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "andaman and nicobar",
    "chandigarh",
    "dadra and nagar haveli",
    "daman and diu",
    "delhi",
    "jammu and kashmir",
    "ladakh",
    "lakshadweep",
    "puducherry",
)

INDIAN_CITIES: tuple[str, ...] = (
    'Achalpur', 'Adityapur', 'Adoni', 'Agartala', 'Agra', 'Ahilyanagar', 'Ahmedabad',
    'Ahmednagar', 'Aizawl', 'Ajmer', 'Akola', 'Alandur', 'Alappuzha', 'Aligarh', 'Alwar',
    'Amaravathi', 'Amaravati', 'Ambala', 'Ambarnath', 'Ambattur', 'Ambernath', 'Amedabad',
    'Amravati', 'Amritsar', 'Amroha', 'Anand', 'Anantapur', 'Anantnag', 'Arrah', 'Asansol',
    'Aurangabad', 'Avadi', 'Badlapur', 'Bagaha', 'Bahadurgarh', 'Baharampur', 'Bahraich',
    'Bally', 'Bangalore', 'Baranagar', 'Barasat', 'Bardhaman', 'Bareilly', 'Barshi',
    'Batala', 'Bathinda', 'Beed', 'Begusarai', 'Belgaum', 'Bellary', 'Berhampur', 'Bettiah',
    'Bhagalpur', 'Bhalswa Jahangir Pur', 'Bharatpur', 'Bharuch', 'Bhatpara', 'Bhavnagar',
    'Bhilai', 'Bhilwara', 'Bhimavaram', 'Bhind', 'Bhiwandi', 'Bhiwani', 'Bhopal',
    'Bhubaneswar', 'Bhusawal', 'Bidar', 'Bidhan Nagar', 'Bihar Sharif', 'Bijapur',
    'Bikaner', 'Bilaspur', 'Bokaro', 'Bokaro Steel City', 'Bongaigaon', 'Budaun',
    'Bulandshahr', 'Burhanpur', 'Buxar', 'Chandannagar', 'Chandigarh', 'Chandrapur',
    'Chapra', 'Chennai', 'Chhapra', 'Chhatrapati Sambhajinagar', 'Chittoor', 'Coimbatore',
    'Cuddalore', 'Cuttack', 'Danapur', 'Darbhanga', 'Davanagere', 'Dehradun', 'Dehri',
    'Delhi', 'Deoghar', 'Deoli', 'Dewas', 'Dhanbad', 'Dharmavaram', 'Dhule', 'Dibrugarh',
    'Dimapur', 'Dindigul', 'Durg', 'Durgapur', 'Eluru', 'Erode', 'Etawah', 'Faizabad',
    'Faridabad', 'Farrukhabad', 'Fatehpur', 'Firozabad', 'Gadag-Betageri', 'Gandhidham',
    'Gandhinagar', 'Gaya', 'Ghaziabad', 'Giridih', 'Gondia', 'Gopalpur', 'Gorakhpur',
    'Greater Noida', 'Gudivada', 'Gulbarga', 'Guna', 'Guntakal', 'Guntur', 'Gurgaon',
    'Guwahati', 'Gwalior', 'Hajipur', 'Haldia', 'Hapur', 'Haridwar', 'Hastsal',
    'Hazaribagh', 'Hindupur', 'Hinganghat', 'Hisar', 'Hoshiarpur', 'Hospet', 'Hosur',
    'Howrah', 'Hubballi-Dharwad', 'Hubli–Dharwad', 'Hugli-Chuchura', 'Hyderabad',
    'Ichalkaranji', 'Imphal', 'Indore', 'Jabalpur', 'Jaipur', 'Jalandhar', 'Jalgaon',
    'Jalna', 'Jamalpur', 'Jammu', 'Jamnagar', 'Jamshedpur', 'Jaunpur', 'Jehanabad',
    'Jhansi', 'Jind', 'Jodhpur', 'Jorhat', 'Junagadh', 'Kadapa', 'Kakinada', 'Kalaburagi',
    'Kalyan-Dombivali', 'Kalyan-Dombivli', 'Kamarhati', 'Kancheepuram', 'Kanpur',
    'Karaikudi', 'Karawal Nagar', 'Karimnagar', 'Karnal', 'Katihar', 'Kavali', 'Khammam',
    'Khandwa', 'Kharagpur', 'Khora', 'Kirari Suleman Nagar', 'Kishanganj', 'Kishangarh',
    'Kochi', 'Kolhapur', 'Kolkata', 'Kollam', 'Korba', 'Kota', 'Kozhikode', 'Kulti',
    'Kurnool', 'Latur', 'Loni', 'Lucknow', 'Ludhiana', 'Machilipatnam', 'Madanapalle',
    'Madhyamgram', 'Madurai', 'Mahbubnagar', 'Mahesana', 'Maheshtala', 'Malda', 'Malegaon',
    'Mangalore', 'Mango', 'Mathura', 'Mau', 'Maunath Bhanjan', 'Medinipur', 'Meerut',
    'Mira-Bhayandar', 'Miryalaguda', 'Mirzapur', 'Moradabad', 'Morena', 'Morvi', 'Motihari',
    'Mumbai', 'Munger', 'Murwara', 'Muzaffarnagar', 'Muzaffarpur', 'Mysore', 'Nadiad',
    'Nagaon', 'Nagercoil', 'Nagpur', 'Naihati', 'Nanded', 'Nanded Waghala', 'Nandurbar',
    'Nandyal', 'Nangloi Jat', 'Narasaraopet', 'Nashik', 'Navi Mumbai', 'Navsari', 'Nellore',
    'New Delhi', 'Nizamabad', 'Noida', 'North Dum Dum', 'North Dumdum', 'Ongole', 'Orai',
    'Osmanabad', 'Ozhukarai', 'Pali', 'Pallavaram', 'Panchkula', 'Panihati', 'Panipat',
    'Panvel', 'Parbhani', 'Patiala', 'Patna', 'Pimpri-Chinchwad', 'Pondicherry',
    'Prayagraj', 'Proddatur', 'Proddutur', 'Puducherry', 'Pune', 'Puri', 'Purnia',
    'Raebareli', 'Raichur', 'Raiganj', 'Raipur', 'Rajahmundry', 'Rajarhat', 'Rajkot',
    'Rajnandgaon', 'Rajpur Sonarpur', 'Ramagundam', 'Rampur', 'Ranchi', 'Ratlam',
    'Raurkela Industrial Township', 'Rewa', 'Rohtak', 'Rourkela', 'Sagar', 'Saharanpur',
    'Saharsa', 'Salem', 'Sambalpur', 'Sambhal', 'Sangli-Miraj & Kupwad', 'Sasaram',
    'Satara', 'Satna', 'Secunderabad', 'Serampore', 'Shahjahanpur', 'Shimla', 'Shimoga',
    'Shivamogga', 'Shivpuri', 'Sikar', 'Silchar', 'Siliguri', 'Singrauli', 'Sirsa',
    'Sitapur', 'Siwan', 'Solapur', 'Sonipat', 'South Dum Dum', 'South Dumdum',
    'Sri Ganganagar', 'Srikakulam', 'Srinagar', 'Sultan Pur Majra', 'Surat',
    'Surendranagar Dudhrej', 'Suryapet', 'Tadepalligudem', 'Tadipatri', 'Tambaram',
    'Tenali', 'Tezpur', 'Thane', 'Thanesar', 'Thanjavur', 'Thiruvananthapuram',
    'Thoothukudi', 'Thrissur', 'Tinsukia', 'Tiruchirappalli', 'Tirunelveli', 'Tirupati',
    'Tiruppur', 'Tiruvottiyur', 'Tonk', 'Tumkur', 'Udaipur', 'Udgir', 'Ujjain',
    'Ulhasnagar', 'Uluberia', 'Unnao', 'Uttarpara Kotrung', 'Vadodara', 'Vapi', 'Varanasi',
    'Vasai-Virar', 'Vellore', 'Veraval', 'Vidisha', 'Vijayanagaram', 'Vijayawada',
    'Visakhapatnam', 'Vizianagaram', 'Warangal', 'Wardha', 'Yamunanagar', 'Yavatmal',
)  # fmt: skip

INDIAN_PLACE_NAMES: tuple[str, ...] = tuple(
    sorted({*INDIAN_CITIES, *(s.title() for s in INDIAN_STATE_UT_NAMES)})
)
