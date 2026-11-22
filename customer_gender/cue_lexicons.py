"""Cue families for customer gender. Data only: no weights and no decisions.

A  agent addresses the customer (sir, ma'am, Mr, Mrs)
B  spouse word about the customer (my/your husband or wife)
C  customer says who they are (her son, his wife)
D  customer states their own first name, and the name is in a list
E  agent uses a Hindi address term for the customer

"Customer" is the caller, not the patient. A name or honorific that refers to
the doctor or the patient is not a cue. Those drops happen in gender_scoring.
"""

from __future__ import annotations

# Surface forms. Matching is case-insensitive.
MALE_ADDRESS = ("sir", "mr", "mister")
FEMALE_ADDRESS = ("ma'am", "madam", "mrs", "ms", "miss")

MALE_RELATION = ("husband",)
FEMALE_RELATION = ("wife",)

# Hindi address terms. "ji" is not gendered. "beta" is included only as a
# direct address; "my beta" is about a child and is not matched.
MALE_HINDI = ("bhai", "bhaiya", "beta")
FEMALE_HINDI = ("didi", "behen")

# Used only after "my name is". Unisex names are left out on purpose.
MALE_NAMES = frozenset({
    "adil", "amit", "arinveer", "devansh", "hamid", "imran", "kartik", "mehul",
    "mohammad", "mohammed", "naren", "prakash", "pranav", "rahul", "rajesh",
    "rayan", "ritesh", "rohit", "sajid", "sameer", "suresh", "vijay", "vikram",
})
FEMALE_NAMES = frozenset({
    "aisha", "anaya", "anita", "divya", "farina", "fatima", "geeta", "kavita",
    "lata", "leena", "mala", "meera", "nandita", "neha", "nisha", "pooja",
    "poonam", "priya", "rekha", "renu", "saira", "sneha", "sunita", "zara",
})
