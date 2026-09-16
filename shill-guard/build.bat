@echo off
set JAVA_HOME=D:\Environment\JAVA17\jdk
set PATH=%JAVA_HOME%\bin;%PATH%
D:\Environment\Maven3.9.9\apache-maven-3.9.9\bin\mvn.cmd compile -f "%~dp0pom.xml" > "%~dp0build_output.txt" 2>&1
if %errorlevel% == 0 (
    echo BUILD SUCCESS
) else (
    echo BUILD FAILURE - see build_output.txt
)
