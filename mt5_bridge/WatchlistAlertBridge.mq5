//+------------------------------------------------------------------+
//|                                       WatchlistAlertBridge.mq5    |
//|  Raises a native MetaTrader 5 Alert() for each new line written   |
//|  by the MT5 Order Manager watchlist.                              |
//|                                                                   |
//|  The app writes alerts to <Common>\Files\mt5om_alerts.txt; this   |
//|  indicator reads the same file via FILE_COMMON and calls Alert(). |
//|                                                                   |
//|  INSTALL:                                                         |
//|    1. Copy this file to <MT5 data folder>\MQL5\Indicators\        |
//|       (in MetaEditor: File > Open Data Folder from the terminal). |
//|    2. In MetaEditor, open it and press Compile (F7).              |
//|    3. In the terminal, drag "WatchlistAlertBridge" from the       |
//|       Navigator onto ANY open chart. Leave it attached.           |
//|    Native MT5 alerts will then fire whenever the app raises one.  |
//+------------------------------------------------------------------+
#property indicator_chart_window
#property indicator_plots 0
#property strict

input int InpPollSeconds = 2;   // how often to check for new alerts

string FileName    = "mt5om_alerts.txt";
long   g_last_size = 0;

//--- file size in bytes (0 if missing)
long CurrentSize()
{
   int h = FileOpen(FileName, FILE_READ | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE)
      return 0;
   long s = FileSize(h);
   FileClose(h);
   return s;
}

int OnInit()
{
   g_last_size = CurrentSize();   // skip lines that already exist on attach
   EventSetTimer(InpPollSeconds);
   Print("WatchlistAlertBridge active — watching ", FileName,
         " (", g_last_size, " bytes already present)");
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   int h = FileOpen(FileName, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;

   long size = FileSize(h);
   if(size <= g_last_size)
   {
      if(size < g_last_size)   // file was truncated/rotated — resync
         g_last_size = size;
      FileClose(h);
      return;
   }

   FileSeek(h, g_last_size, SEEK_SET);   // g_last_size is always at a line boundary
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      if(StringLen(line) > 0)
         Alert(line);
   }
   g_last_size = size;
   FileClose(h);
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   return(rates_total);
}
//+------------------------------------------------------------------+
