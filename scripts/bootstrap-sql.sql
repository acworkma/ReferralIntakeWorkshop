:setvar FunctionIdentityName "id-referralintake-func-dev"
:setvar ContainerAppsIdentityName "id-referralintake-aca-dev"

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '$(FunctionIdentityName)')
  CREATE USER [$(FunctionIdentityName)] FROM EXTERNAL PROVIDER;
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '$(ContainerAppsIdentityName)')
  CREATE USER [$(ContainerAppsIdentityName)] FROM EXTERNAL PROVIDER;

ALTER ROLE db_datareader ADD MEMBER [$(FunctionIdentityName)];
ALTER ROLE db_datawriter ADD MEMBER [$(FunctionIdentityName)];
ALTER ROLE db_ddladmin ADD MEMBER [$(FunctionIdentityName)];
ALTER ROLE db_datareader ADD MEMBER [$(ContainerAppsIdentityName)];
ALTER ROLE db_datawriter ADD MEMBER [$(ContainerAppsIdentityName)];
ALTER ROLE db_ddladmin ADD MEMBER [$(ContainerAppsIdentityName)];
