"""Generate the bundled sample datasets in data/sample/.

These are small, hand-authored, *representative* slices that mirror the schema
and content of the real public datasets (Eclipse/Mozilla Bugzilla exports and
Apache JIRA exports) — including real stack traces, duplicate links, and fix
notes — so the whole pipeline is demoable without downloading anything.

Run:  python scripts/make_sample_data.py
"""
from __future__ import annotations

import csv
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample"
OUT.mkdir(parents=True, exist_ok=True)

JAVA_NPE = (
    "java.lang.NullPointerException\n"
    "\tat org.eclipse.ui.internal.SaveHandler.execute(SaveHandler.java:142)\n"
    "\tat org.eclipse.ui.internal.WorkbenchPage.saveEditor(WorkbenchPage.java:2311)\n"
    "\tat org.eclipse.jface.action.Action.runWithEvent(Action.java:499)\n"
    "Caused by: java.lang.NullPointerException: editorInput was null\n"
    "\tat org.eclipse.ui.internal.EditorManager.getInput(EditorManager.java:88)\n"
)
HADOOP_NPE = (
    "java.lang.NullPointerException\n"
    "\tat org.apache.hadoop.hdfs.server.namenode.BlockManager.processReport(BlockManager.java:1934)\n"
    "\tat org.apache.hadoop.hdfs.server.namenode.NameNodeRpcServer.blockReport(NameNodeRpcServer.java:1521)\n"
    "\tat org.apache.hadoop.ipc.Server$Handler.run(Server.java:2278)\n"
)
SPARK_OOM = (
    "java.lang.OutOfMemoryError: Java heap space\n"
    "\tat org.apache.spark.util.collection.ExternalAppendOnlyMap.insert(ExternalAppendOnlyMap.scala:191)\n"
    "\tat org.apache.spark.shuffle.BlockStoreShuffleReader.read(BlockStoreShuffleReader.scala:104)\n"
    "\tat org.apache.spark.rdd.RDD.iterator(RDD.scala:337)\n"
)
AIRFLOW_TRACE = (
    "Traceback (most recent call last):\n"
    '  File "/usr/local/lib/python3.10/site-packages/airflow/jobs/scheduler_job.py", line 1487, in _run_scheduler_loop\n'
    "    self._do_scheduling(session)\n"
    '  File "/usr/local/lib/python3.10/site-packages/sqlalchemy/engine/base.py", line 1802, in execute\n'
    "    return connection._execute_clauseelement(elem, multiparams, params)\n"
    "sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) server closed the connection unexpectedly\n"
)
JS_TRACE = (
    "TypeError: can't access property \"length\", arr is null\n"
    "    at map (resource://gre/modules/ArrayUtils.js:52:18)\n"
    "    at loadBookmarks (resource://app/modules/Bookmarks.js:210:9)\n"
    "    at async init (resource://app/modules/Startup.js:88:5)\n"
)

# --------------------------------------------------------------------------
BUGZILLA_COLS = [
    "bug_id", "product", "component", "bug_severity", "priority", "short_desc",
    "description", "bug_status", "resolution", "dup_id", "resolution_note",
    "reporter", "assigned_to", "creation_ts", "delta_ts",
]

ECLIPSE = [
    ["1001", "Platform", "UI", "major", "P2",
     "NullPointerException when saving editor with unsaved changes",
     "Steps to reproduce:\n1. Open a file in the text editor\n2. Make changes\n3. Ctrl+S\n\nActual: NPE is thrown and the file is not saved.\n\n" + JAVA_NPE,
     "RESOLVED", "FIXED", "", "Added null guard on editorInput in EditorManager.getInput; added regression test.",
     "amber", "kai", "2011-03-04 09:12:00", "2011-03-09 14:00:00"],
    ["1002", "JDT", "Core", "critical", "P1",
     "ClassCastException in type inference for generic methods",
     "When inferring the type of a chained generic method call the compiler throws:\n"
     "java.lang.ClassCastException: org.eclipse.jdt.core.dom.SimpleType cannot be cast to org.eclipse.jdt.core.dom.ParameterizedType\n"
     "\tat org.eclipse.jdt.internal.compiler.lookup.Scope.inferTypeArguments(Scope.java:4120)",
     "RESOLVED", "FIXED", "", "Handle SimpleType in inferTypeArguments before casting.",
     "deepa", "kai", "2011-05-11 10:00:00", "2011-05-20 16:30:00"],
    ["1003", "Platform", "SWT", "major", "P3",
     "Editor freezes (UI thread deadlock) when opening very large files",
     "Opening a 50MB log file freezes the IDE. UI thread is blocked in synchronous read; jstack shows a deadlock between Display.syncExec and the file loader.",
     "RESOLVED", "FIXED", "", "Moved file loading off the UI thread; load asynchronously with progress.",
     "sam", "lena", "2011-06-01 08:00:00", "2011-06-15 12:00:00"],
    ["1004", "Platform", "Resources", "normal", "P3",
     "Memory leak: workspace holds references to closed projects",
     "After closing and reopening projects many times, heap grows unbounded. A profiler shows ProjectDescription instances are never released.",
     "RESOLVED", "FIXED", "", "Clear listener registrations on project close.",
     "amber", "lena", "2011-06-20 09:30:00", "2011-07-02 11:00:00"],
    ["1005", "JDT", "Debug", "minor", "P4",
     "Breakpoint markers not cleared after project delete",
     "Deleting a project leaves stale breakpoint markers in the Breakpoints view.",
     "RESOLVED", "WONTFIX", "", "Working as intended; markers cleared on restart.",
     "raj", "", "2011-07-05 14:00:00", "2011-07-06 09:00:00"],
    ["1006", "Platform", "UI", "major", "P2",
     "IllegalStateException in workbench during shutdown",
     "On exit the workbench sometimes logs:\njava.lang.IllegalStateException: Widget is disposed\n"
     "\tat org.eclipse.swt.widgets.Widget.checkWidget(Widget.java:485)\n"
     "\tat org.eclipse.ui.internal.WorkbenchWindow.close(WorkbenchWindow.java:1102)",
     "RESOLVED", "FIXED", "", "Check isDisposed() before closing window widgets on shutdown.",
     "sam", "kai", "2011-08-01 10:00:00", "2011-08-10 15:00:00"],
    ["1007", "Platform", "UI", "major", "P2",
     "Saving a file throws NPE in SaveHandler.execute",
     "Every save attempt throws a NullPointerException from SaveHandler. Same trace as reported elsewhere.\n" + JAVA_NPE,
     "RESOLVED", "DUPLICATE", "1001", "",
     "victor", "", "2011-03-08 11:00:00", "2011-03-08 12:00:00"],
    ["1008", "Platform", "Text", "normal", "P3",
     "Find/Replace dialog ignores the case-sensitive option",
     "Enabling 'Case sensitive' in Find/Replace has no effect; matches are still case-insensitive.",
     "RESOLVED", "FIXED", "", "Propagate caseSensitive flag to the search engine.",
     "nina", "lena", "2011-09-01 09:00:00", "2011-09-05 10:00:00"],
    ["1009", "JDT", "Core", "blocker", "P1",
     "OutOfMemoryError building a large workspace",
     "A full build of a 2000-file workspace fails with java.lang.OutOfMemoryError: GC overhead limit exceeded in the compiler's type binding cache.",
     "RESOLVED", "FIXED", "", "Bounded the type binding cache with an LRU; reduced retained heap by 60%.",
     "deepa", "kai", "2011-10-02 08:00:00", "2011-10-20 17:00:00"],
    ["1010", "Platform", "UI", "normal", "P3",
     "Dark theme: tree selection color is unreadable",
     "In the dark theme, selected rows in Package Explorer use dark text on a dark background.",
     "NEW", "", "", "", "nina", "", "2012-01-10 09:00:00", ""],
    ["1011", "Equinox", "p2", "major", "P2",
     "Update fails with BundleException on restart",
     "Applying an update then restarting fails:\norg.osgi.framework.BundleException: Could not resolve module\n"
     "\tat org.eclipse.osgi.container.Module.start(Module.java:444)",
     "RESOLVED", "FIXED", "", "Refresh the resolver state before restart.",
     "raj", "lena", "2012-02-01 10:00:00", "2012-02-14 12:00:00"],
    ["1012", "Platform", "UI", "minor", "P4",
     "Tooltip flickers on hover in Package Explorer",
     "Hovering over long file names makes the tooltip flicker rapidly.",
     "RESOLVED", "WORKSFORME", "", "Cannot reproduce on current build.",
     "victor", "", "2012-03-01 09:00:00", "2012-03-03 09:00:00"],
]

MOZILLA = [
    ["2001", "Firefox", "General", "critical", "P1",
     "Crash on startup [@ mozilla::layers::CompositorBridgeParent]",
     "Firefox crashes immediately on launch on Linux with hardware acceleration enabled. Crash signature points to the compositor bridge.",
     "RESOLVED", "FIXED", "", "Null-check the widget before creating the compositor session.",
     "pat", "quinn", "2013-04-01 09:00:00", "2013-04-12 15:00:00"],
    ["2002", "Core", "JavaScript", "major", "P2",
     "TypeError: can't access property length of null in Array map polyfill",
     "Loading bookmarks throws a TypeError from the ArrayUtils map polyfill when the input is null.\n" + JS_TRACE,
     "RESOLVED", "FIXED", "", "Guard against null input in ArrayUtils.map.",
     "lee", "quinn", "2013-05-03 10:00:00", "2013-05-09 11:00:00"],
    ["2003", "Firefox", "Bookmarks", "normal", "P3",
     "Bookmarks lost after a crash during sync",
     "If the browser crashes mid-sync, the local bookmarks database is truncated and entries are lost.",
     "RESOLVED", "FIXED", "", "Write bookmarks atomically via a temp file + rename.",
     "pat", "morgan", "2013-06-01 08:00:00", "2013-06-20 12:00:00"],
    ["2004", "Core", "Networking", "major", "P2",
     "Memory leak in HTTP cache under heavy load",
     "Under sustained load, RSS grows steadily; the HTTP cache never evicts entries whose channels errored out.",
     "RESOLVED", "FIXED", "", "Release cache entries on channel error.",
     "lee", "morgan", "2013-07-01 09:00:00", "2013-07-15 10:00:00"],
    ["2005", "Firefox", "General", "critical", "P1",
     "Browser crashes at startup on Linux with GPU acceleration",
     "Same as the compositor startup crash. Happens on every launch with WebRender enabled.",
     "RESOLVED", "DUPLICATE", "2001", "",
     "sky", "", "2013-04-05 09:00:00", "2013-04-05 10:00:00"],
    ["2006", "Core", "DOM", "major", "P2",
     "Null pointer dereference in nsDocument::Destroy",
     "Closing a tab quickly after load sometimes crashes:\nSegmentation fault in nsDocument::Destroy (nsDocument.cpp:3120)",
     "RESOLVED", "FIXED", "", "Check mPresShell for null before teardown.",
     "pat", "quinn", "2013-08-01 09:00:00", "2013-08-18 12:00:00"],
    ["2007", "Firefox", "Address Bar", "minor", "P4",
     "Autocomplete suggests already-deleted history entries",
     "Deleted history entries still appear as awesomebar suggestions until restart.",
     "RESOLVED", "WONTFIX", "", "Deferred; suggestion cache refresh is expensive.",
     "sky", "", "2013-09-01 09:00:00", "2013-09-02 09:00:00"],
    ["2008", "Core", "Graphics", "major", "P2",
     "WebGL context lost causes the tab to freeze",
     "When the GPU driver resets, the WebGL context is lost and the tab hangs instead of recovering.",
     "NEW", "", "", "", "lee", "", "2014-01-05 09:00:00", ""],
    ["2009", "Firefox", "Preferences", "normal", "P3",
     "Settings search returns no results for 'proxy'",
     "Typing 'proxy' in the settings search box returns nothing even though proxy settings exist.",
     "RESOLVED", "FIXED", "", "Index the connection settings section for search.",
     "morgan", "quinn", "2014-02-01 09:00:00", "2014-02-06 10:00:00"],
    ["2010", "Core", "JavaScript", "critical", "P1",
     "Infinite recursion (stack overflow) in Promise resolution",
     "A self-resolving promise causes InternalError: too much recursion and crashes the JS engine.",
     "RESOLVED", "FIXED", "", "Detect self-resolution and reject with TypeError per spec.",
     "lee", "quinn", "2014-03-01 09:00:00", "2014-03-14 12:00:00"],
]

JIRA_COLS = [
    "key", "project", "issuetype", "summary", "description", "priority", "status",
    "resolution", "components", "duplicate_of", "resolution_note",
    "reporter", "assignee", "created", "resolutiondate",
]

APACHE = [
    ["HADOOP-101", "HADOOP", "Bug",
     "NullPointerException in NameNode when block report arrives during safemode",
     "The NameNode throws an NPE if a DataNode block report arrives while the node is still in safemode and the BlockManager is not fully initialized.\n" + HADOOP_NPE,
     "Major", "Resolved", "Fixed", "namenode", "",
     "Guarded block report handling against a null BlockManager during safemode; added a null check and a unit test.",
     "arun", "todd", "2012-01-10", "2012-01-24"],
    ["SPARK-202", "SPARK", "Bug",
     "OutOfMemoryError: Java heap space during shuffle with large partitions",
     "Shuffle-heavy jobs fail with OOM when a single partition does not fit in memory.\n" + SPARK_OOM,
     "Critical", "Resolved", "Fixed", "Spark Core", "",
     "Enabled spill-to-disk for the shuffle map; fixed an accumulator leak. Tune spark.shuffle.spill.numElementsForceSpillThreshold.",
     "matei", "reynold", "2014-03-02", "2014-03-19"],
    ["KAFKA-303", "KAFKA", "Bug",
     "TimeoutException: Expiring records for topic after 30000 ms",
     "Producers intermittently fail with org.apache.kafka.common.errors.TimeoutException when the broker metadata is stale during a leader election.",
     "Major", "Resolved", "Fixed", "producer", "",
     "Fixed a metadata refresh deadlock; increased default request.timeout.ms and documented retries.",
     "jun", "jason", "2015-06-01", "2015-06-15"],
    ["HADOOP-104", "HADOOP", "Bug",
     "NPE in NameNode processing block report during safemode on startup",
     "Same NullPointerException path as reported before — block report during safemode hits a null BlockManager.\n" + HADOOP_NPE,
     "Major", "Resolved", "Duplicate", "namenode", "HADOOP-101", "",
     "steve", "", "2012-01-15", "2012-01-16"],
    ["AIRFLOW-405", "AIRFLOW", "Bug",
     "Scheduler crashes with sqlalchemy OperationalError: server closed the connection",
     "The scheduler dies after a few hours when the Postgres connection is dropped by the server.\n" + AIRFLOW_TRACE,
     "Critical", "Resolved", "Fixed", "scheduler", "",
     "Set pool_recycle and pool_pre_ping on the SQLAlchemy engine; retry on OperationalError.",
     "maxime", "kaxil", "2018-07-01", "2018-07-20"],
    ["SPARK-206", "SPARK", "Bug",
     "Task not serializable: NotSerializableException for closure capturing SparkContext",
     "A map closure that references a field of the driver class captures the whole SparkContext and fails with org.apache.spark.SparkException: Task not serializable.",
     "Major", "Resolved", "Fixed", "Spark Core", "",
     "Extract the needed value into a local val (or broadcast it) so the closure does not capture SparkContext.",
     "matei", "reynold", "2014-05-02", "2014-05-12"],
    ["HBASE-507", "HBASE", "Bug",
     "RegionServer aborts with IOException: Too many open files",
     "Under high region count the RegionServer aborts because it exhausts file descriptors while opening HFiles.",
     "Blocker", "Resolved", "Fixed", "regionserver", "",
     "Fixed a file-handle leak in HFileReader; documented raising the OS ulimit.",
     "stack", "lars", "2013-09-01", "2013-09-22"],
    ["KAFKA-308", "KAFKA", "Bug",
     "ConcurrentModificationException during consumer group rebalance",
     "java.util.ConcurrentModificationException is thrown while iterating assigned partitions during a rebalance.\n"
     "\tat java.util.HashMap$HashIterator.nextNode(HashMap.java:1445)\n"
     "\tat org.apache.kafka.clients.consumer.internals.ConsumerCoordinator.onJoinComplete(ConsumerCoordinator.java:279)",
     "Major", "Resolved", "Fixed", "consumer", "",
     "Copy the assignment set before iterating; synchronize rebalance callbacks.",
     "jun", "jason", "2015-08-01", "2015-08-18"],
    ["FLINK-609", "FLINK", "Bug",
     "Checkpoint expired before completing under backpressure",
     "Checkpoints time out and expire when the job is under sustained backpressure, eventually failing the job.",
     "Major", "Open", "Unresolved", "Runtime / Checkpointing", "", "",
     "aljoscha", "", "2017-02-01", ""],
    ["AIRFLOW-408", "AIRFLOW", "Bug",
     "DAG import error: ModuleNotFoundError after upgrade",
     "After upgrading, DAGs that import a local plugin fail with ModuleNotFoundError: No module named 'plugins'.\n"
     "Traceback (most recent call last):\n"
     '  File "/opt/airflow/dags/etl.py", line 3, in <module>\n'
     "    from plugins.hooks import MyHook\n"
     "ModuleNotFoundError: No module named 'plugins'",
     "Major", "Resolved", "Fixed", "DagBag", "",
     "Add the plugins directory to sys.path; document AIRFLOW__CORE__PLUGINS_FOLDER / PYTHONPATH.",
     "maxime", "kaxil", "2018-09-01", "2018-09-10"],
    ["HADOOP-110", "HADOOP", "Improvement",
     "Improve NameNode metrics for safemode transitions",
     "Add counters and timers around safemode entry/exit to aid debugging. (Not a defect — improvement.)",
     "Minor", "Resolved", "Fixed", "namenode", "", "Added safemode metrics.",
     "arun", "todd", "2012-02-01", "2012-02-10"],
    ["SPARK-210", "SPARK", "Bug",
     "Deadlock between BlockManager and MemoryStore under high concurrency",
     "Two threads acquire the BlockManager and MemoryStore locks in opposite order, producing a deadlock during eviction under load.",
     "Critical", "Resolved", "Fixed", "Spark Core", "",
     "Impose a consistent lock ordering; take the MemoryStore lock before the BlockInfo lock.",
     "matei", "reynold", "2014-07-01", "2014-07-25"],
]


def write_csv(path: Path, cols: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(cols)
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path.relative_to(path.parent.parent.parent)}")


if __name__ == "__main__":
    write_csv(OUT / "eclipse_bugs.csv", BUGZILLA_COLS, ECLIPSE)
    write_csv(OUT / "mozilla_bugs.csv", BUGZILLA_COLS, MOZILLA)
    write_csv(OUT / "apache_issues.csv", JIRA_COLS, APACHE)
    print("Sample data ready.")
