# Customer 360 Data Dictionary

Last updated: 2024-01-15

This dictionary defines the business meaning of every field in the `customer_360` dataset for
onboarding, analytics and Copilot grounding.

## Customer ID
Unique identifier assigned to a customer at the moment of account creation. Used as the
canonical join key across every downstream system.

## Customer Name
Full legal name of the customer as captured during registration.

## Customer Email
Registered email address used for account communication and login.

## Customer Status
A value describing where the customer currently stands in their relationship with us.

## Revenue
Total revenue attributed to the customer over the trailing twelve months, expressed in EUR.

## Loyalty Ref
This field contains PII (personally identifiable information): the loyalty reference number
can be linked back to a specific individual through the loyalty program registry, even though
the technical column name gives no indication of that on its own.

## Customer Segment
(No definition has been provided for this field yet.)
