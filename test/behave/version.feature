Feature: mycroft-version-checker

  Scenario: What version
    Given an english speaking user
     When the user says "What is your version"
     Then "mycroft-version-checker" should reply with dialog from "version.dialog"

  Scenario: Current version
    Given an english speaking user
     When the user says "What is the current version"
     Then "mycroft-version-checker" should reply with dialog from "version.dialog"

