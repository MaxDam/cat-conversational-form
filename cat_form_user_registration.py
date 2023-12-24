from cat.mad_hatter.decorators import tool, hook
from cat.log import log
from typing import Dict
from .cform import CForm, cform
from pydantic import Field


class UserRegistration(CForm):
    name:    str | None = None
    surname: str | None = None
    company: str | None = None
    email:   str | None = None

    '''
    name:    str | None = Field(description="Name of the user who wants to register")
    surname: str | None = Field(description="Surname of the user who wants to register")
    company: str | None = Field(description="Company where the user who wants to register works")
    email:   str | None = Field(description="Email of the user who wants to register")
    '''


@cform(UserRegistration)
def execute_action(cat, model):
    result = "<h3>You have registered<h3><br>" 
    result += "<table border=0>"
    result += "<tr>"
    result += "   <td>Name</td>"
    result += f"  <td>{model.name}</td>"
    result += "</tr>"
    result += "<tr>"
    result += "   <td>Surname</td>"
    result += f"  <td>{model.surname}</td>"
    result += "</tr>"
    result += "<tr>"
    result += "   <td>Company</td>"
    result += f"  <td>{model.company}</td>"
    result += "</tr>"
    result += "<tr>"
    result += "   <td>Email</td>"
    result += f"  <td>{model.email}</td>"
    result += "</tr>"
    result += "</table>"
    return result


@cform(UserRegistration)
def get_prompt_examples():
    return [
            {
                "sentence": "Hello, I would register me for this service",
                "json": [None, None, None, None],
                "updatedJson": [None, None, None, None]
            },
            {
                "sentence": "Hello, my surname is Smith",
                "json": ["John", None, None, None],
                "updatedJson": ["John", "Smith", None, None]
            }
        ]


# Start intent
@tool(return_direct=True)
def start_register_intent(input, cat):
    """I would register the user for the service"""
    log.critical("INTENT USER REGISTRATION START")
    return UserRegistration.start(cat)


# Stop intent
@tool()
def stop_register_intent(input, cat):
    """I don't want to continue this user registration"""
    log.critical("INTENT USER REGISTRATION STOP")
    return UserRegistration.stop(cat)    


# Order pizza handle conversation
@hook()
def agent_fast_reply(fast_reply: Dict, cat) -> Dict:
    return UserRegistration.dialogue(cat)
