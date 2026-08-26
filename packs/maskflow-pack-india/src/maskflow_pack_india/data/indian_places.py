"""Bundled Indian place-name gazetteer for INDIAN_ADDRESS L1 matching
(../gazetteer.py) -- states/UTs + top cities/towns by population.

INDIAN_STATE_UT_NAMES is the same 36-entry list this pack already used for
PIN_CODE's context keywords (moved here from __init__.py, re-exported there
unchanged so that registration is unaffected).

INDIAN_CITIES: 554 city/town names. The original 368 (fetched 2026-08-26 from
Wikipedia's "List of cities in India by population",
https://en.wikipedia.org/wiki/List_of_cities_in_India_by_population,
CC-BY-SA 4.0 + GFDL) are unioned with 186 more added 2026-08-27 from India's
Census 2011 town-population figures (Government of India, Government Open
Data License - India / GODL-India -- population counts are official
statistics, not a copyrightable compilation; retrieved via a CSV mirror of
the Kaggle "Top 500 Indian Cities" release,
https://github.com/siddharthjain1611/Top-500-Indian-cities, itself sourced
from the same Census figures) filtered to population >= 100,000 -- 492
qualifying towns, of which 306 were already covered. 554 clears the work
order's "top-500" target; see docs/data-refresh.md for the refresh
procedure (`scripts/refresh_india_reference_data.py cities`). A number of
alternate-spelling/transliteration near-duplicates from both sources
(Amaravathi/Amaravati, Hubballi-Dharwad/Hubli-Dharwad/Hubli–Dharwad,
Ahmedabad/Ahmadabad, Bengaluru/Bangalore, ...) are kept as separate entries
deliberately -- all spellings are real-world usage and matching any of them
is the point of a gazetteer.

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
    'Abohar', 'Achalpur', 'Adilabad', 'Adityapur', 'Adoni', 'Agartala', 'Agra',
    'Ahilyanagar', 'Ahmadabad', 'Ahmadnagar', 'Ahmedabad', 'Ahmednagar', 'Aizawl', 'Ajmer',
    'Akbarpur', 'Akola', 'Alandur', 'Alappuzha', 'Aligarh', 'Allahabad', 'Alwar',
    'Amaravathi', 'Amaravati', 'Ambala', 'Ambala Sadar', 'Ambarnath', 'Ambattur',
    'Ambernath', 'Ambikapur', 'Ambur', 'Amedabad', 'Amravati', 'Amreli', 'Amritsar',
    'Amroha', 'Anand', 'Anantapur', 'Anantnag', 'Arrah', 'Asansol',
    'Ashoknagar Kalyangarh', 'Aurangabad', 'Avadi', 'Azamgarh', 'Badlapur', 'Bagaha',
    'Bagalkot', 'Bahadurgarh', 'Baharampur', 'Bahraich', 'Baidyabati', 'Baleshwar Town',
    'Ballia', 'Bally', 'Bally City', 'Balurghat', 'Banda', 'Bangalore', 'Bankura',
    'Bansberia', 'Banswara', 'Baran', 'Baranagar', 'Barasat', 'Baraut', 'Barddhaman',
    'Bardhaman', 'Bareilly', 'Baripada Town', 'Barnala', 'Barrackpur', 'Barshi',
    'Basirhat', 'Basti', 'Batala', 'Bathinda', 'Beawar', 'Beed', 'Begusarai', 'Belgaum',
    'Bellary', 'Bengaluru', 'Berhampur', 'Bettiah', 'Betul', 'Bhadrak', 'Bhadravati',
    'Bhadreswar', 'Bhagalpur', 'Bhalswa Jahangir Pur', 'Bharatpur', 'Bharuch', 'Bhatpara',
    'Bhavnagar', 'Bhilai', 'Bhilai Nagar', 'Bhilwara', 'Bhimavaram', 'Bhind', 'Bhiwadi',
    'Bhiwandi', 'Bhiwani', 'Bhopal', 'Bhubaneswar', 'Bhubaneswar Town', 'Bhuj', 'Bhusawal',
    'Bid', 'Bidar', 'Bidhan Nagar', 'Bihar Sharif', 'Biharsharif', 'Bijapur', 'Bikaner',
    'Bilaspur', 'Bokaro', 'Bokaro Steel City', 'Bongaigaon', 'Bongaon', 'Botad',
    'Brahmapur Town', 'Budaun', 'Bulandshahr', 'Bundi', 'Burari', 'Burhanpur', 'Buxar',
    'Champdani', 'Chandannagar', 'Chandausi', 'Chandigarh', 'Chandrapur', 'Chapra', 'Chas',
    'Chennai', 'Chhapra', 'Chhatrapati Sambhajinagar', 'Chhattarpur', 'Chhindwara',
    'Chikmagalur', 'Chilakaluripet', 'Chitradurga', 'Chittaurgarh', 'Chittoor', 'Churu',
    'Coimbatore', 'Cuddalore', 'Cuttack', 'Dabgram', 'Dallo Pura', 'Damoh', 'Danapur',
    'Darbhanga', 'Darjiling', 'Datia', 'Davanagere', 'Deesa', 'Dehradun', 'Dehri', 'Delhi',
    'Delhi Cantonment', 'Deoghar', 'Deoli', 'Deoria', 'Dewas', 'Dhanbad', 'Dharmavaram',
    'Dhaulpur', 'Dhule', 'Dibrugarh', 'Dimapur', 'Dinapur Nizamat', 'Dindigul', 'Dum Dum',
    'Durg', 'Durgapur', 'Eluru', 'English Bazar', 'Erode', 'Etah', 'Etawah', 'Faizabad',
    'Faridabad', 'Farrukhabad', 'Farrukhabad-cum-Fatehgarh', 'Fatehpur', 'Firozabad',
    'Firozpur', 'Gadag-Betageri', 'Gadag-Betigeri', 'Gandhidham', 'Gandhinagar',
    'Ganganagar', 'Gangapur City', 'Gangawati', 'Gaya', 'Ghaziabad', 'Ghazipur', 'Giridih',
    'Godhra', 'Gokal Pur', 'Gonda', 'Gondal', 'Gondia', 'Gondiya', 'Gopalpur', 'Gorakhpur',
    'Greater Hyderabad', 'Greater Mumbai', 'Greater Noida', 'Gudivada', 'Gulbarga', 'Guna',
    'Guntakal', 'Guntur', 'Gurgaon', 'Guwahati', 'Gwalior', 'Habra', 'Hajipur', 'Haldia',
    'Haldwani-cum-Kathgodam', 'Halisahar', 'Hanumangarh', 'Haora', 'Hapur', 'Hardoi',
    'Hardwar', 'Haridwar', 'Hassan', 'Hastsal', 'Hathras', 'Hazaribag', 'Hazaribagh',
    'Hindaun', 'Hindupur', 'Hinganghat', 'Hisar', 'Hoshangabad', 'Hoshiarpur', 'Hospet',
    'Hosur', 'Howrah', 'Hubballi-Dharwad', 'Hubli-Dharwad', 'Hubli–Dharwad',
    'Hugli-Chinsurah', 'Hugli-Chuchura', 'Hyderabad', 'Ichalkaranji', 'Imphal', 'Indore',
    'Jabalpur', 'Jagadhri', 'Jagdalpur', 'Jaipur', 'Jalandhar', 'Jalgaon', 'Jalna',
    'Jalpaiguri', 'Jamalpur', 'Jammu', 'Jamnagar', 'Jamshedpur', 'Jamuria', 'Jaunpur',
    'Jehanabad', 'Jetpur Navagadh', 'Jhansi', 'Jhunjhunun', 'Jind', 'Jodhpur', 'Jorhat',
    'Junagadh', 'Kadapa', 'Kaithal', 'Kakinada', 'Kalaburagi', 'Kalol', 'Kalyan-Dombivali',
    'Kalyan-Dombivli', 'Kalyani', 'Kamarhati', 'Kancheepuram', 'Kanchrapara', 'Kanpur',
    'Kanpur City', 'Karaikkudi', 'Karaikudi', 'Karawal Nagar', 'Karimnagar', 'Karnal',
    'Kasganj', 'Kashipur', 'Katihar', 'Kavali', 'Khammam', 'Khandwa', 'Khanna',
    'Kharagpur', 'Khardaha', 'Khargone', 'Khora', 'Khurja', 'Kirari Suleman Nagar',
    'Kishanganj', 'Kishangarh', 'Kochi', 'Kolar', 'Kolhapur', 'Kolkata', 'Kollam', 'Korba',
    'Kota', 'Kozhikode', 'Krishnanagar', 'Kulti', 'Kumbakonam', 'Kurichi', 'Kurnool',
    'Lakhimpur', 'Lalitpur', 'Latur', 'Loni', 'Lucknow', 'Ludhiana', 'Machilipatnam',
    'Madanapalle', 'Madavaram', 'Madhyamgram', 'Madurai', 'Mahbubnagar', 'Mahesana',
    'Maheshtala', 'Mainpuri', 'Malda', 'Malegaon', 'Malerkotla', 'Mandoli', 'Mandsaur',
    'Mandya', 'Mangalore', 'Mango', 'Mathura', 'Mau', 'Maunath Bhanjan', 'Medinipur',
    'Meerut', 'Mira Bhayander', 'Mira-Bhayandar', 'Miryalaguda', 'Mirzapur',
    'Mirzapur-cum-Vindhyachal', 'Modinagar', 'Moga', 'Moradabad', 'Morena', 'Morvi',
    'Motihari', 'Mughalsarai', 'Muktsar', 'Mumbai', 'Munger', 'Murwara', 'Mustafabad',
    'Muzaffarnagar', 'Muzaffarpur', 'Mysore', 'Nabadwip', 'Nadiad', 'Nagaon',
    'Nagapattinam', 'Nagaur', 'Nagda', 'Nagercoil', 'Nagpur', 'Naihati', 'Nalgonda',
    'Nanded', 'Nanded Waghala', 'Nandurbar', 'Nandyal', 'Nangloi Jat', 'Narasaraopet',
    'Nashik', 'Navi Mumbai', 'Navi Mumbai Panvel Raigarh', 'Navsari', 'Neemuch', 'Nellore',
    'New Delhi', 'Neyveli', 'Nizamabad', 'Noida', 'North Barrackpur', 'North Dum Dum',
    'North Dumdum', 'Ongole', 'Orai', 'Osmanabad', 'Ozhukarai', 'Palakkad', 'Palanpur',
    'Pali', 'Pallavaram', 'Palwal', 'Panchkula', 'Panihati', 'Panipat', 'Panvel',
    'Parbhani', 'Patan', 'Pathankot', 'Patiala', 'Patna', 'Pilibhit', 'Pimpri Chinchwad',
    'Pimpri-Chinchwad', 'Pithampur', 'Pondicherry', 'Porbandar', 'Port Blair', 'Prayagraj',
    'Proddatur', 'Proddutur', 'Puducherry', 'Pudukkottai', 'Pune', 'Puri', 'Purnia',
    'Puruliya', 'Rae Bareli', 'Raebareli', 'Raichur', 'Raiganj', 'Raigarh', 'Raipur',
    'Rajahmundry', 'Rajapalayam', 'Rajarhat', 'Rajarhat Gopalpur', 'Rajkot', 'Rajnandgaon',
    'Rajpur Sonarpur', 'Ramagundam', 'Rampur', 'Ranchi', 'Ranibennur', 'Raniganj',
    'Ratlam', 'Raurkela Industrial Township', 'Raurkela Town', 'Rewa', 'Rewari', 'Rishra',
    'Robertson Pet', 'Rohtak', 'Roorkee', 'Rourkela', 'Rudrapur', 'S.A.S. Nagar', 'Sagar',
    'Saharanpur', 'Saharsa', 'Salem', 'Sambalpur', 'Sambhal', 'Sangli Miraj Kupwad',
    'Sangli-Miraj & Kupwad', 'Santipur', 'Sasaram', 'Satara', 'Satna', 'Sawai Madhopur',
    'Secunderabad', 'Sehore', 'Seoni', 'Serampore', 'Shahjahanpur', 'Shamli', 'Shikohabad',
    'Shillong', 'Shimla', 'Shimoga', 'Shivamogga', 'Shivpuri', 'Sikar', 'Silchar',
    'Siliguri', 'Singrauli', 'Sirsa', 'Sitapur', 'Siwan', 'Solapur', 'Sonipat',
    'South Dum Dum', 'South Dumdum', 'Sri Ganganagar', 'Srikakulam', 'Srinagar',
    'Sujangarh', 'Sultan Pur Majra', 'Sultanpur', 'Surat', 'Surendranagar Dudhrej',
    'Suryapet', 'Tadepalligudem', 'Tadipatri', 'Tadpatri', 'Tambaram', 'Tenali', 'Tezpur',
    'Thane', 'Thanesar', 'Thanjavur', 'Thiruvananthapuram', 'Thoothukkudi', 'Thoothukudi',
    'Thrissur', 'Tinsukia', 'Tiruchirappalli', 'Tirunelveli', 'Tirupati', 'Tiruppur',
    'Tiruvannamalai', 'Tiruvottiyur', 'Titagarh', 'Tonk', 'Tumkur', 'Udaipur', 'Udgir',
    'Udupi', 'Ujjain', 'Ulhasnagar', 'Uluberia', 'Unnao', 'Uttarpara Kotrung', 'Vadodara',
    'Valsad', 'Vapi', 'Varanasi', 'Vasai Virar City', 'Vasai-Virar', 'Vellore', 'Veraval',
    'Vidisha', 'Vijayanagaram', 'Vijayawada', 'Visakhapatnam', 'Vizianagaram', 'Warangal',
    'Wardha', 'Yamunanagar', 'Yavatmal',)  # fmt: skip

INDIAN_PLACE_NAMES: tuple[str, ...] = tuple(
    sorted({*INDIAN_CITIES, *(s.title() for s in INDIAN_STATE_UT_NAMES)})
)
