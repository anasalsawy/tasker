import React from 'react';
import {
  DialogContainer,
  DialogOverlay,
  DialogHeader,
  HeaderEnd,
  DialogTitle,
  DialogContent,
  DialogActions
} from './DialogElements';
import {
  IconButton
} from '../Button';
import { IoMdClose } from 'react-icons/io';
import { Divider } from '../SmallElements';
import { useSelector } from 'react-redux';

const Dialog = ({ child, maxWidth, isOpen, setOpen, persistant, title=null, flex=true, padding, scrollable=false, actions=null, isDarkMode=false }) => {

  const onOverlayClick = () => {
    if (persistant !== true) {
      setOpen(false);
    }
  };

  const isRTL = useSelector(state => state.isRTL);

  return (
    <>
      {
        isOpen ? 
        <>
          <DialogOverlay onClick={onOverlayClick} />
          <DialogContainer maxWidth={maxWidth} isDarkMode={isDarkMode}>
            <DialogHeader>
              {
                title !== null ?
                <DialogTitle isDarkMode={isDarkMode}>
                  {title}
                </DialogTitle> :
                <></>
              }
              <HeaderEnd isRTL={isRTL}>
                <IconButton onClick={() => setOpen(false)} iconSize="30px" color={isDarkMode ? "rgba(255, 255, 255, 0.75)" : "rgba(0, 0, 0, 0.75)"}>
                  <IoMdClose />
                </IconButton>
              </HeaderEnd>
            </DialogHeader>
            <Divider color={isDarkMode ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.2)'} style={{marginBottom: '10px'}} />
            {
              flex ? <DialogContent padding={padding} scrollable={scrollable}>
                {child}
              </DialogContent> : child
            }
            {
              actions !== null ? <DialogActions>
                {actions}
              </DialogActions> : <></>
            }
          </DialogContainer>
        </> : <></>
      }
    </>
  )
};

export default Dialog;
