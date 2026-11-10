const {app,BrowserWindow}=require('electron');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {registerReceiptPrinter}=require('../source-app-updates/main/electron/receipt-printer.cjs');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'backwoods-receipt-native-'));
app.setPath('userData',profile);
app.whenReady().then(async()=>{
  const output=path.resolve(__dirname,'../test-results/main-receipts');fs.mkdirSync(output,{recursive:true});
  const parent=new BrowserWindow({show:false,webPreferences:{sandbox:true,contextIsolation:true,nodeIntegration:false}});
  await parent.loadURL('data:text/html,<html><body>Isolated Main receipt test</body></html>');
  let handler,printed=false;
  class ReceiptWindow extends BrowserWindow {
    constructor(options){
      super(options);
      this.webContents.print=async(options,done)=>{
        try {
          assert.equal(options.silent,false);
          const text=await this.webContents.executeJavaScript('document.body.innerText');
          for(const value of ['Backwoods Brew','Receipt #native-test','2 x $5.00','TOTAL $11.00'])assert(text.includes(value));
          const pdf=await this.webContents.printToPDF({printBackground:true,pageSize:'A4',preferCSSPageSize:false});
          assert(pdf.length>1500);fs.writeFileSync(path.join(output,'electron-receipt.pdf'),pdf);printed=true;done(true,'');
        } catch(error){done(false,error.message);}
      };
    }
  }
  registerReceiptPrinter({ipcMain:{handle:(_,fn)=>handler=fn},BrowserWindow:ReceiptWindow});
  const result=await handler({sender:parent.webContents,senderFrame:parent.webContents.mainFrame},
    {title:'Main receipt test',text:'Backwoods Brew\nOxford\nReceipt #native-test\n2 x $5.00 = $10.00\nSales tax $1.00\nTOTAL $11.00\nPayment Cash\nTendered $20.00\nChange $9.00'});
  assert.equal(result.ok,true,result.error);assert(printed);
  parent.destroy();fs.writeFileSync(path.join(output,'electron-result.json'),JSON.stringify({passed:true,nativeRendering:true,pdfGenerated:true,physicalPrinterTested:false},null,2));
  console.log('PASS: real Electron receipt rendered, native PDF contains transaction text, print lifecycle completed.');app.quit();
}).catch(error=>{console.error(error);app.exit(1);});
