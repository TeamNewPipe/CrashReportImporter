# NewPipe Crash Report Importer

This little Python application makes NewPipe's developers' lifes easier.


## Background
NewPipe was added an automatic crash reporter that composes an e-mail
containing a JSON string that the user may or may not send to the developers.

But as there's so many crash reports (2000-3000 a month at the moment),
we quickly needed a solution to aggregate those reports based on specific
criteria.

A tool that is capable of doing exactly everything we needed and more
(displays some neat statistics and reports for example, and preprocesses
all the collected meta data) is [Sentry](https://docs.sentry.io).

But, as things are never *easy*, there was no real tool around that satisfied
both our requirements for data privacy and transparency (the Sentry
client for Android does not show what exactly is sent to the server for
example), which is why we initially decided to build those JSON blobs and
have the users send those via e-mail to us.

Now all we needed was some tool that imported those mails from IMAP into
Sentry using its RESTful API.

*NewPipe Crash Report Importer was born.*


## State of the project

This project is just lots of alpha code, there's no unit tests or similar, it
is only tested on a local development instance of Sentry.

Usually works as expected. Probably not useful for anyone else though, except
you're trying to build your own Python-based custom Sentry client, too.

One of the bigger problems that were solved with some effort included the
literally broken data that some mail clients send in.

We did our best to get this to work well, and it can import about 90% of all
incoming mails. This is satisfying enough for us.

This tool will probably not see any more functional updates as we plan to
replace it using some HTTP transport. This will be more convenient.

This is one of the reasons you don't find a "how to run" at the moment,
although this might change in the future. Just open an issue, and we'll
try to provide one.

**Note:** This application requires Python 3.5 or higher.


## License

The MIT License (MIT)
Copyright (c) 2016 TheAssassin

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
IN THE SOFTWARE.
