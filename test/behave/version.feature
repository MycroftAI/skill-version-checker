Feature: mycroft-version-checker

  Scenario Outline: What version
    Given an english speaking user
     When the user says "<what is your current version>"
     Then "mycroft-version-checker" should reply with dialog from "version.dialog"

    Examples: What is your current version
      | what is your current version |
      | what is your version |
      | what is the current version |
      | what version are you running |
      | find the version |
