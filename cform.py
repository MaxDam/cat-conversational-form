import json
from cat.log import log
from pydantic import ValidationError, BaseModel
from cat.looking_glass.stray_cat import StrayCat
from cat.looking_glass.prompts import MAIN_PROMPT_PREFIX
from enum import Enum
import guardrails as gd


# Collect several cform annotated functions
cform_functions = []

# Decorator @cform with form_name parameter
def cform(model):
    def decorator(func):
        cform_functions.append((func, model))
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Conversational Form State
class CFormState(Enum):
    ASK_INFORMATIONS    = 0
    ASK_SUMMARY         = 1


# Class Conversational Form
class CForm(BaseModel):

    _state :            CFormState
    _key :              str
    _cat :              StrayCat
    _model_is_updated : bool
    _language :         str
    _prompt_prefix :    str
    _ask_for :          []
    _is_completed       : bool
    _dialog_is_skipped  : bool
    
    def __init__(self, key, cat):
        super().__init__()
        self._state = CFormState.ASK_INFORMATIONS
        self._key = key
        self._cat = cat
        
        self._model_is_updated   = False
        self._language = self.get_language()
        self._dialog_is_skipped = True

        # Get prompt, user message and chat history
        self._prompt_prefix = self._cat.mad_hatter.execute_hook("agent_prompt_prefix", MAIN_PROMPT_PREFIX, cat=self._cat)
        

    # Get model fields
    def get_model(self):
        return self.dict(exclude={"_.*"})
    
    
    ### ASK INFORMATIONS ###

    # Queries the llm asking for the missing fields of the form, without memory chain
    def ask_missing_information(self) -> str:
       
        # Prompt
        prompt = f"Imagine you have to fill out a registration form and some information is missing.\n\
        Please ask to provide missing details. Missing information can be found in the ask_for list.\n\
        Example:\n\
        if ask_for list is provided by [name, address]\n\
        ask: may I know your name?\n\
        Ask for one piece of information at a time.\n\
        Be sure to maintain a friendly and professional tone when requesting this information.\n\
        using {self._language} language.\n\n\
        ### ask_for list: {self._ask_for}"
        print(f'prompt: {prompt}')

        '''
        prompt = f"Below is are some things to ask the user for in a coversation way.\n\
        You should only ask one question at a time even if you don't get all the info.\n\
        Don't ask as a list! Don't greet the user! Don't say Hi.\n\
        Explain you need to get some info.\n\
        If the ask_for list is empty then thank them and ask how you can help them. \n\
        Ask only one question at a time\n\n\
        ### ask_for list: {self._ask_for}\n\n\
        using {self._language} language."
        '''

        response = self._cat.llm(prompt)
        return response 


    # Queries the lllm asking for the fields to be modified in the form, without a memory chain
    def ask_change_information(self) -> str:
       
        #Prompt
        prompt = f"Your form contains all the necessary information, show the summary of the data\n\
        present in the completed form and ask the user if he wants to change something.\n\
        ### form data: {self.get_model()}\n\
        using the {self._language} language."
        print(f'prompt: {prompt}')

        response = self._cat.llm(prompt)
        return response 


    # Fill list of empty form's fields
    def check_what_fields_are_empty(self):
        ask_for = []
        
        for field, value in self.get_model().items():
            if value in [None, "", 0]:
                ask_for.append(f'{field}')

        self._ask_for = ask_for
        self._is_completed = not self._ask_for


    # Enrich the user message with missing informations
    def enrich_user_message(self):
        
        # Get user message
        user_message = self._cat.working_memory["user_message_json"]["text"]

        # Set prompt
        if not self._is_completed:
            user_message = f"{user_message}\n\
                (Remember that you are still missing the following information to complete the form:\n\
                Missing informations: {self._ask_for})"
        else:
            user_message = f"{user_message}\n\
                (Remember that you have completed filling out the form and need user confirmation.\n\
                Form data: {self.get_model()})"

        # Set user_message with the new user_message
        self._cat.working_memory["user_message_json"]["text"] = user_message

    
    # Get language
    def get_language(self):

        # Get user message
        user_message = self._cat.working_memory["user_message_json"]["text"]

        # Prompt
        language_prompt = f"Identify the language of the following message \
        and return only the language of the message, without other text.\n\
        If you can't locate it, return 'English'.\n\
        Message examples:\n\
        'Ciao, come stai?', returns: 'Italian',\n\
        'How do you go?', returns 'English',\n\
        'Bonjour a tous', returns 'French'\n\n\
        Message: '{user_message}'"
        
        # Queries the LLM and check if user is agree or not
        response = self._cat.llm(language_prompt)
        log.critical(f'Language: {response}')
        return response


    ### SUMMARIZATION ###

    # Show summary of the form to the user
    def show_summary(self, cat):
        
        # Prompt
        prompt = f"You have collected the following information from the user:\n\
        ### form data: {self.get_model()}\n\n\
        Summarize the information contained in the form data.\n\
        Next, ask the user to confirm whether the information collected is correct.\n\
        Using {self._language} language."
        print(f'prompt: {prompt}')

        '''
        prompt = f"Show the summary of the data in the completed form and ask the user if they are correct.\n\
            Don't ask irrelevant questions.\n\
            Try to be precise and detailed in describing the form and what you need to know.\n\n\
            ### form data: {self.get_model()}\n\n\
            using {self._language} language."
        '''
        
        # Queries the LLM
        response = self._cat.llm(prompt)
        return response


    # Check user confirm the form data
    def check_user_confirm(self) -> bool:
        
        # Get user message
        user_message = self._cat.working_memory["user_message_json"]["text"]
        
        # Confirm prompt
        confirm_prompt = f"only respond with YES if the user's message is affirmative\
        or NO if the user message is negative, do not answer the other way.\n\
        If you are unsure, answer NO.\n\n\
        ### user message: {user_message}" 
        print(f'confirm prompt: {confirm_prompt}')

        '''
        confirm_prompt = f"Given a sentence that I will now give you,\n\
        just respond with 'YES' or 'NO' depending on whether the sentence is:\n\
        - a refusal either has a negative meaning or is an intention to cancel the form (NO)\n\
        - an acceptance has a positive or neutral meaning (YES).\n\
        If you are unsure, answer 'NO'.\n\
        The sentence is as follows:\n\
        ### user message: {user_message}"
        '''
        
        # Queries the LLM and check if user is agree or not
        response = self._cat.llm(confirm_prompt)
        log.critical(f'check_user_confirm: {response}')
        confirm = "NO" not in response and "YES" in response
        
        return confirm


    ### UPDATE JSON ###

    # Updates the form with the information extracted from the user's response
    # (Return True if the model is updated)
    def update_from_user_response(self):

        # Extract new info
        user_response_json = self._extract_info()
        #user_response_json = self._extract_info_with_guardrails()
        if user_response_json is None:
            return False
        
        # Gets a new_model with the new fields filled in
        new_model = self.get_model()
        for attribute, value in user_response_json.items():
            if value not in [None, ""]:
                new_model[attribute] = value

        # Check if there is no information in the new_model that can update the form
        if new_model == self.get_model():
            return False

        #TODO IT DOES NOT WORK, need to check why
        # Validate new_model (raises ValidationError exception on error)
        #self.model_validate_json(**new_model)
        
        # Overrides the current model with the new_model
        for attribute, value in new_model.items():
            if hasattr(self, attribute):
                setattr(self, attribute, value)

        log.critical(f'MODEL : {self.get_model()}')
        return True


    # Extracted new informations from the user's response (from sratch)
    def _extract_info(self):
        user_message = self._cat.working_memory["user_message_json"]["text"]
        prompt = self._get_pydantic_prompt(user_message)
        print(f'prompt: {prompt}')
        json_str = self._cat.llm(prompt)
        user_response_json = json.loads(json_str)
        return user_response_json


    # return pydantic prompt based from examples
    def _get_pydantic_prompt(self, message):
        lines = []
        
        prompt_examples = self.get_prompt_examples()
        for example in prompt_examples:
            lines.append(f"Sentence: {example['sentence']}")
            lines.append(f"JSON: {self._format_prompt_json(example['json'])}")
            lines.append(f"Updated JSON: {self._format_prompt_json(example['updatedJson'])}")
            lines.append("\n")

        result = "Update the following JSON with information extracted from the Sentence:\n\n"
        result += "\n".join(lines)
        result += f"Sentence: {message}\nJSON:{json.dumps(self.get_model(), indent=4)}\nUpdated JSON:"
        return result


    # format json for prompt
    def _format_prompt_json(self, values):
        #attributes = list(self.get_model().__annotations__.keys())
        attributes = list(self.get_model().keys())
        data_dict = dict(zip(attributes, values))
        return json.dumps(data_dict, indent=4)


    # Get prompt examples
    def get_prompt_examples(self):
        # Get the class name
        class_name = self.__class__.__name__
        
        # Look for methods annotated with @Action and with model equal to the curren class
        for func, model in cform_functions:
            if hasattr(model, "__name__") and model.__name__ == class_name and func.__name__ == 'get_prompt_examples':
                return func()

        # Default result
        return []


    #TODO IT DOES NOT WORK, need to check why
    # Extracted new informations from the user's response (using guardrails library)
    def _extract_info_with_guardrails(self):
        
        # Get user message
        user_message = self._cat.working_memory["user_message_json"]["text"]
        
        # Prompt
        prompt = """
        Given the following client message, please extract information about his form.

        ${message}

        ${gr.complete_json_suffix_v2}
        """
        print(f'prompt: {prompt}')

        # Get json from guardrails
        guard = gd.Guard.from_pydantic(output_class=self.__class__, prompt=prompt)
        result = guard(self._cat._llm, prompt_params={"message": user_message})
        return result
    
        '''
        # Print the validated output from the LLM
        print(result)
        print(json.dumps(result.validated_output, indent=2))

        user_response_json = json.loads(result)
        return user_response_json
        '''


    ### EXECUTE DIALOGUE ###

    # Check that there is only one active form
    def set_active_form(self):
        if "_active_cforms" not in self._cat.working_memory.keys():
            self._cat.working_memory["_active_cforms"] = []
        if self._key not in self._cat.working_memory["_active_cforms"]:
            self._cat.working_memory["_active_cforms"].append(self._key)
        for key in self._cat.working_memory["_active_cforms"]:
            if key != self._key:
                self._cat.working_memory["_active_cforms"].remove(key)
                if key in self._cat.working_memory.keys():
                    del self._cat.working_memory[key]


    # Execute the dialogue step
    def execute_dialogue(self):
        
        try:
            # update form from user response
            self._model_is_updated = self.update_from_user_response()
            
            # Fill the information it should ask the user based on the fields that are still empty
            self.check_what_fields_are_empty()
            log.warning(f'MISSING INFORMATIONS: {self._ask_for}')
            
            # (Cat's breath) Check if it's time to skip the conversation step
            if self._check_skip_conversation_step(): 
                log.critical(f'> SKIP CONVERSATION STEP {self._key}')

                # Enrich user message with missing informations and return None
                self.enrich_user_message()

                # Set dialog as skipped and return None
                self._dialog_is_skipped = True
                return None
    
        except ValidationError as e:
            # If there was a validation problem, return the error message
            message = e.errors()[0]["msg"]
            response = self._cat.llm(message)
            log.critical('> RETURN ERROR')
            return response

        # Set dialogue as unskipped
        self._dialog_is_skipped = False

        log.warning(f"state:{self._state}, is completed:{self._is_completed}")

        # If the form is not completed, ask for missing information
        if not self._is_completed:
            self._state  = CFormState.ASK_INFORMATIONS
            response = self.ask_missing_information()
            log.critical(f'> ASK MISSING INFORMATIONS {self._key}')
            return response

        # If the form is completed and state == ASK_SUMMARY ..
        if self._state in [CFormState.ASK_SUMMARY]:
            
            # Check confirm from user answer
            if self.check_user_confirm():

                # Execute action
                log.critical(f'> EXECUTE ACTION {self._key}')
                return self.execute_action()
        
        # If the form is completed and state == ASK_INFORMATIONS ..
        if self._state in [CFormState.ASK_INFORMATIONS]:
            
            # Get settings
            settings = self._cat.mad_hatter.get_plugin().load_settings()
            
            # If ask_confirm is true, show summary and ask confirmation
            if settings["ask_confirm"] is True:
                
                # Show summary
                response = self.show_summary(self._cat)

                # Change status in ASK_SUMMARY
                self._state = CFormState.ASK_SUMMARY
        
                log.critical('> SHOW SUMMARY')
                return response
            
            else: #else, execute action
                log.critical(f'> EXECUTE ACTION {self._key}')
                return self.execute_action()

        # If the form is completed, ask for missing information
        self._state  = CFormState.ASK_INFORMATIONS
        response = self.ask_change_information()
        log.critical(f'> ASK CHANGE INFORMATIONS {self._key}')
        return response
   

    # (Cat's breath) Check if should skip conversation step
    def _check_skip_conversation_step(self):

        # If the model was updated, don't skip conversation step
        if self._model_is_updated is True:
            return False
        
        # If the dialogue was previously skipped, it doesn't skip it again
        if self._dialog_is_skipped is True:
            return False

        '''# If the form is complete, don't skip conversation step 
        if self._is_completed is True:
            return False'''

        # If the state is starded or summary, don't skip conversation step
        if self._state in [CFormState.ASK_SUMMARY]:
            return False

        # If they aren't called tools, don't skip conversation step
        num_called_tools = len(self._cat.working_memory["procedural_memories"])
        if num_called_tools == 0:
            return False
    
        # Else, skip conversation step
        return True


    # Execute final form action
    def execute_action(self):
        # Get the class name
        class_name = self.__class__.__name__

        # Look for methods annotated with @Action and with model equal to the curren class
        for func, model in cform_functions:
            if hasattr(model, "__name__") and model.__name__ == class_name and func.__name__ == 'execute_action':
                del self._cat.working_memory[self._key]
                return func(self._cat, self)

        # Default result
        del self._cat.working_memory[self._key]
        return self.get_model()   


    # CLASS METHODS
    
    # Start conversation
    # (typically inside the tool that starts the intent)
    @classmethod
    def start(cls, cat):
        key = cls.__name__
        if key not in cat.working_memory.keys():
            cform = cls(key, cat)
            cat.working_memory[key] = cform
        cform = cat.working_memory[key]
        cform.set_active_form()
        response = cform.execute_dialogue()
        return response


    # Stop conversation
    # (typically inside the tool that stops the intent)
    @classmethod
    def stop(cls, cat):
        key = cls.__name__
        if key in cat.working_memory.keys():
            del cat.working_memory[key]
        return


    # Execute the dialogue step
    # (typically inside the agent_fast_reply hook)
    @classmethod
    def dialogue(cls, cat):
        key = cls.__name__
        if key in cat.working_memory.keys():
            cform = cat.working_memory[key]
            response = cform.execute_dialogue()
            if response:
                return { "output": response }
        return
