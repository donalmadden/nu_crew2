from typing import Any, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import requests
import json
import os

class GithubProjectFetcherToolSchema(BaseModel):
    """Input for GithubProjectFetcherToo."""

    project_id: str = Field(..., description="Mandatory full github project_id")


class GithubProjectFetcherTool(BaseTool):
    """A tool for reading all content of a github project.

    This tool inherits its schema handling from BaseTool to avoid recursive schema
    definition issues. The args_schema is set to GithubProjectFetcherToolSchema which defines
    the required project_id parameter. The schema should not be overridden in the
    constructor as it would break the inheritance chain and cause infinite loops.

    The tool supports two ways of specifying the url path:
    1. At construction time via the project_id parameter
    2. At runtime via the project_id parameter in the tool's input

    Args:
        project_id (Optional[str]): Path to the github project to be read. If provided,
            this becomes the default url path for the tool.
        **kwargs: Additional keyword arguments passed to BaseTool.

    Example:
        >>> tool = GithubProjectFetcherTool(project_id="my_project_id_")
        >>> content = tool.run()  # Reads my_project_id_
        >>> content = tool.run(project_id="other_project_id_")  # Reads other.txt
    """

    name: str = "Reading all tickets within a github project"
    description: str = "A tool that grabs all tickets of a github project. To use this tool, provide a 'project_id' parameter with the id of the github project you want to read."
    args_schema: Type[BaseModel] = GithubProjectFetcherToolSchema
    project_id: Optional[str] = None

    def __init__(self, project_id: Optional[str] = None, **kwargs: Any) -> None:
        """Initialize the GithubProjectFetcherTool.

        Args:
            project_id (Optional[str]): id of the github project to be read. If provided,
                this becomes the default project id for the tool.
            **kwargs: Additional keyword arguments passed to BaseTool.
        """
        if project_id is not None:
            kwargs[
                'description'] = f"A tool that reads github project content. The default project id is {project_id}, but you can provide a different 'project_id' parameter to read another project."

        super().__init__(**kwargs)
        self.project_id = project_id


    def _run(
            self,
            **kwargs: Any,
    ) -> str:
        project_id = kwargs.get("project_id", self.project_id)
        if project_id is None:
            return "Error: No project id provided. Please provide a project id either in the constructor or as an argument."

        try:

            def update_authorization_header(headers, token):
                """
                Update the Authorization header with a new bearer token.

                Args:
                    headers (dict): Existing headers dictionary
                    token (str): New bearer token

                Returns:
                    dict: Updated headers dictionary
                """
                headers["Authorization"] = f"Bearer {token}"
                return headers

            def substitute_id(query, my_nu_id):
                """
                Substitutes the <REPLACE_ME> placeholder with the provided ID in the GraphQL query.

                Args:
                    query (str): The original GraphQL query string
                    my_nu_id (str): The ID to replace the <REPLACE_ME> placeholder

                Returns:
                    str: The modified GraphQL query with the ID substituted
                """
                # Use regex to replace <REPLACE_ME> with the provided ID
                modified_query = query.replace("<REPLACE_ME>", str(my_nu_id))

                return modified_query

            # Extracting and preparing sorting key (status)
            def extract_fields(item):
                status = None
                for field_value in item['fieldValues']['nodes']:
                    if 'name' in field_value and field_value['field']['name'].lower() == 'status':
                        status = field_value['name']
                        break
                return status

            query = """
            fragment projectV2Fields on ProjectV2Item {
              id
              fieldValues(first: 100) {
                nodes {
                  ... on ProjectV2ItemFieldTextValue {
                    text
                    field {
                      ... on ProjectV2FieldCommon {
                        name
                      }
                    }
                  }
                  ... on ProjectV2ItemFieldDateValue {
                    date
                    field {
                      ... on ProjectV2FieldCommon {
                        name
                      }
                    }
                  }
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field {
                      ... on ProjectV2FieldCommon {
                        name
                      }
                    }
                  }
                  ... on ProjectV2ItemFieldNumberValue {
                    number
                    field {
                      ... on ProjectV2FieldCommon {
                        name
                      }
                    }
                  }
                }
              }
              content {
                ... on Issue {
                  body
                  title
                  number
                  repository {
                    name
                  }
                }
              }
            }
            query {
              node(id: "<REPLACE_ME>") {
                ... on ProjectV2 {
                  items(first: 100) {
                    nodes {
                      ...projectV2Fields
                    }
                  }
                }
              }
            }
            """
            modified_query = substitute_id(query,
                project_id)


            # GitHub GraphQL endpoint
            url = "https://api.github.com/graphql"
            headers = {
                "Authorization": "Bearer ",
                "Content-Type": "application/json"
            }

            _headers = update_authorization_header(headers, os.environ.get("GITHUB_AUTH"))

            # Make the request to the GitHub API
            response = requests.post(url, headers=_headers, json={'query': modified_query})
            data = response.json()

            # Extract and process items
            items = data['data']['node']['items']['nodes']

            # Initialize lists for each status
            status_lists = {
                "To be tested": [],
                "In Progress": [],
                "Todo": [],
                "Done": []
            }

            # Process and categorize items
            for item in items:
                content = item.get('content', {})
                title = content.get('title', 'N/A')
                body = content.get('body', '')
                status = extract_fields(item)

                card = {
                    "id": item['id'],
                    "title": title,
                    "body": body,
                    "status": status
                }

                if status in status_lists:
                    if not (card['title'] == 'N/A' and card['body'] == ''):
                        print(card)
                        status_lists[status].append(card)
                else:
                    print(f"Unknown Status: {status}")

            output_to_return = {}

            # Output status lists
            for status, cards in status_lists.items():
                print(f"Status: {status}")
                output_to_return[status] = cards
                for card in cards:
                    print(json.dumps(card, indent=4))
                print("\n")

            return json.dumps(output_to_return)

        except Exception as e:
            return f"Error: Failed to read file {project_id}. {str(e)}"