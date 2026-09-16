"""Every response the chatbot can produce, in one place.

Values in braces are filled exclusively from database records, system
configuration, knowledge-base content, or business rules — never invented.
"""

# --- Greeting / help ---------------------------------------------------------

WELCOME = (
    "Hello! I'm the SAS Reserve assistant. I can answer questions about "
    "facility availability, your reservations, facility schedules and rules, "
    "equipment, and reservation policies. Ask me something, or type \"help\" "
    "to see everything I can do."
)

WELCOME_PUBLIC = (
    "Hello! I'm the SAS Reserve assistant. I can answer questions about "
    "facilities, availability, schedules, policies, and how to register or "
    "log in. Sign in to also ask about your own reservations. Type \"help\" "
    "to see everything I can do."
)

SIGN_IN_REQUIRED = (
    "I can only share reservation details with signed-in users, and only "
    "their own. Please log in and ask again — or type \"how do I register\" "
    "if you don't have an account yet."
)

HELP = (
    "Here is what I can help with:\n"
    "• Availability — \"Is the Audio-Visual Room available tomorrow at 2 PM?\" "
    "or \"What facilities are available on Friday?\"\n"
    "• Your reservations — \"Show my reservations\", \"What are my upcoming "
    "reservations?\" or \"Where is my reservation SAS-2026-00012?\"\n"
    "• Facilities — \"Tell me about the Gymnasium\", \"What are the rules for the "
    "Cafeteria?\", \"What time does the AVR open on Monday?\"\n"
    "• Equipment — \"How many wireless microphones are available today?\"\n"
    "• Maintenance — \"Is any equipment under maintenance?\"\n"
    "• Policies — \"What is the cancellation policy?\", \"How do I make a "
    "reservation?\"\n"
    "• Getting started — \"How do I register?\", \"How do I log in?\", "
    "\"Any announcements?\"\n\n"
    "I answer only from this system's live data — I don't use outside sources."
)

# --- Availability ------------------------------------------------------------

AVAILABLE = (
    "The {facility_name} is available on {date} from {start_time} to {end_time}."
)

AVAILABLE_NO_TIME = "The {facility_name} is available on {date}."

AVAILABLE_PARTIAL = (
    "The {facility_name} is only partially available on {date}. It is booked "
    "{conflicts}. Free windows: {free_windows}."
)

UNAVAILABLE_CONFLICT = (
    "The {facility_name} is unavailable on {date} from {start_time} to "
    "{end_time} because it has an existing reservation: \"{event_name}\" "
    "({conflict_window})."
)

UNAVAILABLE_CONFLICT_NO_EVENT = (
    "The {facility_name} is unavailable on {date} from {start_time} to "
    "{end_time} because it has an existing reservation ({conflict_window})."
)

UNAVAILABLE_MAINTENANCE = (
    "The {facility_name} is unavailable on {date} because it is currently "
    "under maintenance."
)

OUTSIDE_HOURS = (
    "The {facility_name} is open from {open_time} to {close_time} on {day}, "
    "so {start_time} to {end_time} is outside its operating hours."
)

FACILITY_CLOSED = (
    "The {facility_name} is closed on {day} (no operating hours configured)."
)

# --- Facilities --------------------------------------------------------------

FACILITY_INFO = (
    "{facility_name} — {facility_type}\n"
    "Location: {location}\n"
    "Capacity: {capacity} people\n"
    "Status: {status}\n"
    "{description}"
)

FACILITY_RULES = "Rules for the {facility_name}:\n{rules}"

FACILITY_NO_RULES = (
    "There are no specific rules recorded for the {facility_name} in the "
    "system beyond general booking policies."
)

SCHEDULE = "Operating hours for the {facility_name}:\n{hours}"

FACILITY_NOT_FOUND = (
    "I couldn't find a facility named \"{facility_name}\" in the system. "
    "You can ask about: {facility_names}."
)

LIST_FACILITIES = "Facilities available in the system:\n{facilities}"

# --- Reservations ------------------------------------------------------------

MY_RESERVATIONS = "Your reservations:\n{reservations}"

MY_RESERVATIONS_EMPTY = (
    "You currently have no reservations in the system. Create one from the "
    "Reservations page or ask me how to make a reservation."
)

MY_UPCOMING = "You have {count} upcoming reservation(s):\n{reservations}"

MY_UPCOMING_EMPTY = (
    "You have no upcoming reservations. Ask me \"how do I book a facility\" "
    "to create one."
)

MY_CANCELLED = "Your cancelled reservations:\n{reservations}"

MY_CANCELLED_EMPTY = "You have no cancelled reservations in the system."

RESERVATION_FOUND = (
    "Reservation {reservation_id} — \"{event_name}\"\n"
    "Facility: {facility_name}\n"
    "Date: {date} ({day})\n"
    "Time: {start_time} to {end_time}\n"
    "Status: {status}"
)

RESERVATION_NOT_FOUND = (
    "I couldn't find a reservation matching those details. Check the "
    "reservation ID (format SAS-YYYY-#####) or ask \"show my reservations\"."
)

RESERVATION_FORBIDDEN = (
    "That reservation exists, but you are not authorized to view its details."
)

RESERVATION_ID_INCOMPLETE = (
    "That reservation ID looks incomplete. Reservation IDs look like "
    "SAS-2026-00012 — could you double-check it?"
)

# --- Equipment ---------------------------------------------------------------

EQUIPMENT_AVAILABLE = "{name}: {available} of {total} {unit}s available for that time."

EQUIPMENT_NOT_FOUND = "I couldn't find equipment named \"{equipment_name}\" in the system."

EQUIPMENT_NONE = "There is no equipment registered in the system."

# --- Maintenance -------------------------------------------------------------

MAINTENANCE_OPEN = "Equipment currently under maintenance:\n{items}"

MAINTENANCE_NONE = "No equipment is under maintenance right now."

# --- Policies / knowledge base ----------------------------------------------

POLICY_ANSWER = "According to the system's records: {content}"

POLICY_SOURCE = "\n(Source: {title})"

# --- Guidance (read-only chatbot: never mutates data) ------------------------

MAKE_RESERVATION_GUIDE = (
    "I can't create reservations, but it only takes a minute: open the "
    "Reservations page and click \"Create reservation\", or go directly to "
    "/reservations/new. If you tell me the facility, date, and time you want, "
    "I can check availability for you first."
)

MAKE_RESERVATION_PUBLIC = (
    "Reservations are made by signed-in users: log in (or register first), "
    "open the Reservations page, and click \"Create reservation\". If you tell "
    "me the facility, date, and time you want, I can check availability for "
    "you right now."
)

REGISTRATION_GUIDE = (
    "To register: click \"Register\" on the home page (or go to /register) and "
    "fill in your name, email, username, and password. Campus users register "
    "with their school email; external organizations can note their "
    "organization name. Once registered, log in to submit reservations."
)

LOGIN_GUIDE = (
    "To log in: click \"Login\" on the home page (or go to /login) and enter "
    "your username and password. You can also sign in with Google using your "
    "school account. If you forgot your password, contact the SAS Office to "
    "have it reset — the system does not offer self-service password resets."
)

ANNOUNCEMENTS = "Current announcements:\n{items}"

NO_ANNOUNCEMENTS = "There are no announcements in the system right now."

CANCEL_RESERVATION_GUIDE = (
    "I can't cancel reservations, but you can do it yourself: open "
    "/reservations/{reservation_id} and use the Cancel button. Note the "
    "system's rule: {policy_excerpt}"
)

CANCEL_GUIDE_NO_MATCH = (
    "I can't cancel reservations, and I couldn't find a matching reservation "
    "in your records. Open /reservations to see your bookings, or tell me the "
    "reservation ID (SAS-YYYY-#####) and I'll look it up."
)

# --- Fallbacks ---------------------------------------------------------------

NOT_FOUND = "I couldn't find that information in the system."

OUT_OF_SCOPE = (
    "I can only answer questions related to the information available in "
    "this system."
)

UNKNOWN_INTENT = (
    "I'm sorry, I don't understand that request. You can ask me about facility "
    "availability, reservations, facility information, schedules, or "
    "reservation policies."
)

DB_UNAVAILABLE = (
    "The system is currently unable to retrieve the latest information. "
    "Please try again later."
)
